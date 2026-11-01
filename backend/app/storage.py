"""Private shared document storage, local for development and S3 for hosting."""

import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from app.config import get_settings


@lru_cache(maxsize=4)
def s3_client(endpoint, region):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 2},
            s3={"addressing_style": "path"} if endpoint else {},
        ),
    )


def client():
    s = get_settings()
    return s3_client(s.s3_endpoint_url, s.aws_default_region)


def key(name):
    if Path(name).name != name or not name.endswith(".pdf"):
        raise ValueError("Invalid document storage key.")
    return get_settings().s3_prefix + name


def persist_document(path, name):
    settings = get_settings()
    if settings.storage_backend == "s3":
        client().upload_file(
            str(path),
            settings.s3_bucket,
            key(name),
            ExtraArgs={"ContentType": "application/pdf", "ServerSideEncryption": "AES256"},
        )


def remove_document(name):
    settings = get_settings()
    if settings.storage_backend == "s3":
        client().delete_object(Bucket=settings.s3_bucket, Key=key(name))


@contextmanager
def open_document(name):
    settings = get_settings()
    key(name)
    if settings.storage_backend == "local":
        path = settings.storage_dir.resolve() / name
        if not path.is_file():
            raise FileNotFoundError("Document artifact unavailable.")
        yield path
    else:
        with tempfile.TemporaryDirectory(prefix="invoiceguard-document-") as temp:
            path = Path(temp) / name
            body = client().get_object(Bucket=settings.s3_bucket, Key=key(name))["Body"]
            try:
                size = 0
                with path.open("wb") as target:
                    for chunk in body.iter_chunks(65536):
                        size += len(chunk)
                        if size > settings.max_upload_bytes:
                            raise ValueError("Stored document exceeds limit.")
                        target.write(chunk)
            finally:
                body.close()
            yield path
