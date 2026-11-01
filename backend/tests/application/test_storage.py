from io import BytesIO

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.config import get_settings
from app.storage import key, open_document


def test_s3_document_read_is_private_bounded_and_temporary(monkeypatch, tmp_path):
    config = tmp_path / "aws-config"
    config.write_text("[profile synthetic-test]\nregion=us-east-1\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_PROFILE", "synthetic-test")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "synthetic-private")
    get_settings.cache_clear()
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="synthetic-test",
        aws_secret_access_key="synthetic-test",
    )
    body = b"%PDF-synthetic"
    stub = Stubber(client)
    stub.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(body), len(body))},
        {"Bucket": "synthetic-private", "Key": "invoiceguard/example.pdf"},
    )
    monkeypatch.setattr("app.storage.client", lambda: client)
    try:
        with stub, open_document("example.pdf") as path:
            assert path.read_bytes() == body
            retained = path
        assert not retained.exists()
        with pytest.raises(ValueError):
            key("../escape.pdf")
    finally:
        get_settings.cache_clear()
