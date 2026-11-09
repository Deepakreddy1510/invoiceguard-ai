from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")
    database_url: str = (
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/invoiceguard"
    )
    app_environment: str = "local"
    auth_mode: Literal["local", "supabase"] = "local"
    local_workspace_id: UUID = DEMO_WORKSPACE_ID
    supabase_url: str = ""
    supabase_publishable_key: str = ""

    @property
    def supabase_issuer(self):
        return self.supabase_url.rstrip("/") + "/auth/v1"

    frontend_origin: str = "http://localhost:5173"
    storage_dir: Path = Path("../.local/documents")
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_prefix: str = "invoiceguard/"
    s3_endpoint_url: str | None = None
    aws_default_region: str = "us-east-1"
    max_upload_bytes: int = 10 * 1024 * 1024
    gemini_api_key: SecretStr | None = None
    allow_manual_extraction_modes: bool = False
    gemini_model: str = Field(default="gemini-2.5-flash", pattern=r"^[A-Za-z0-9.-]+$")
    gmail_client_id: str = ""
    gmail_client_secret: SecretStr | None = None
    gmail_redirect_uri: str = ""
    gmail_trusted_origin: str = ""
    gmail_encryption_key: SecretStr | None = None
    gmail_poll_seconds: int = Field(default=60, ge=30, le=3600)
    gmail_use_gemini: bool = False
    frontend_dist: Path = Path("../frontend/dist")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value):
        if value.startswith(("postgres://", "postgresql://")):
            return "postgresql+psycopg://" + value.split("://", 1)[1]
        return value

    def validate_runtime(self):
        if self.supabase_publishable_key and not self.supabase_publishable_key.startswith(
            "sb_publishable_"
        ):
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY must be a public publishable key.")
        if self.auth_mode == "supabase":
            from urllib.parse import urlparse

            url = urlparse(self.supabase_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.query
                or url.fragment
                or url.path not in ("", "/")
            ):
                raise RuntimeError("SUPABASE_URL must be an HTTPS project origin.")
            if not self.supabase_publishable_key.startswith("sb_publishable_"):
                raise RuntimeError("SUPABASE_PUBLISHABLE_KEY must be a public publishable key.")
        if self.app_environment != "local":
            if self.auth_mode != "supabase":
                raise RuntimeError(
                    "local-only authentication is forbidden in a hosted environment."
                )
            if self.storage_backend != "s3" or not self.s3_bucket:
                raise RuntimeError("Hosted web and worker require shared private S3 storage.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
