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
    auth_mode: Literal["local", "oidc"] = "local"
    local_workspace_id: UUID = DEMO_WORKSPACE_ID
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_client_id: str = ""
    frontend_origin: str = "http://localhost:5173"
    storage_dir: Path = Path("../.local/documents")
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_prefix: str = "invoiceguard/"
    s3_endpoint_url: str | None = None
    aws_default_region: str = "us-east-1"
    max_upload_bytes: int = 10 * 1024 * 1024
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default="gemini-2.5-flash", pattern=r"^[A-Za-z0-9.-]+$")
    frontend_dist: Path = Path("../frontend/dist")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value):
        if value.startswith(("postgres://", "postgresql://")):
            return "postgresql+psycopg://" + value.split("://", 1)[1]
        return value

    def validate_runtime(self):
        if self.app_environment != "local":
            if self.auth_mode != "oidc":
                raise RuntimeError(
                    "local-only authentication is forbidden in a hosted environment."
                )
            if not all(
                [self.oidc_issuer.startswith("https://"), self.oidc_audience, self.oidc_client_id]
            ):
                raise RuntimeError("Hosted OIDC issuer, audience and client ID are required.")
            if self.storage_backend != "s3" or not self.s3_bucket:
                raise RuntimeError("Hosted web and worker require shared private S3 storage.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
