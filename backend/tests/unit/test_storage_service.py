"""Unit tests for StorageService, mocking the boto3 S3 client -- no real AWS
credentials or network access required, and no moto dependency (a plain
MagicMock standing in for the botocore client is sufficient for this
milestone's scope: verifying StorageService calls boto3 correctly and
translates botocore failures into this module's own exception types)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.services.storage.exceptions import (
    StorageDeleteError,
    StorageNotConfiguredError,
    StoragePresignError,
    StorageUploadError,
)
from app.services.storage.service import StorageService


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        database_url="postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test",
        jwt_secret_key="dev-secret",
        s3_endpoint_url="http://localhost:9000",
        s3_access_key="test-access-key",
        s3_secret_key="test-secret-key",
        s3_bucket="test-bucket",
        s3_region="us-east-1",
        s3_force_path_style=True,
        s3_presigned_url_expire_seconds=300,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _client_error(operation: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": "InternalError", "Message": "boom"}},
        operation_name=operation,
    )


def _service_with_mock_client() -> tuple[StorageService, MagicMock]:
    service = StorageService(_settings())
    mock_client = MagicMock()
    service._client = mock_client  # test-only: swap the real boto3 client for a mock
    return service, mock_client


class TestConstruction:
    def test_construction_does_not_require_network_access(self):
        # boto3.client() never performs I/O -- this must succeed even with
        # placeholder/dev credentials and no reachable endpoint, so local
        # development and app startup are never blocked by storage config.
        StorageService(_settings())

    def test_missing_bucket_raises_not_configured(self):
        with pytest.raises(StorageNotConfiguredError):
            StorageService(_settings(s3_bucket=""))


class TestPut:
    def test_put_calls_boto3_with_expected_arguments(self):
        service, mock_client = _service_with_mock_client()

        result = service.put(
            key="evidence/org/res/file_a.pdf", body=b"hello", content_type="application/pdf"
        )

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="evidence/org/res/file_a.pdf",
            Body=b"hello",
            ContentType="application/pdf",
        )
        assert result.key == "evidence/org/res/file_a.pdf"
        assert result.size_bytes == 5

    def test_put_wraps_client_error(self):
        service, mock_client = _service_with_mock_client()
        mock_client.put_object.side_effect = _client_error("PutObject")

        with pytest.raises(StorageUploadError):
            service.put(key="k", body=b"x", content_type="text/plain")


class TestPresignGet:
    def test_presign_get_calls_boto3_with_default_expiry(self):
        service, mock_client = _service_with_mock_client()
        mock_client.generate_presigned_url.return_value = "https://example.com/signed"

        url = service.presign_get(key="evidence/org/res/file_a.pdf")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "evidence/org/res/file_a.pdf"},
            ExpiresIn=300,
        )
        assert url == "https://example.com/signed"

    def test_presign_get_honors_explicit_expiry(self):
        service, mock_client = _service_with_mock_client()
        mock_client.generate_presigned_url.return_value = "https://example.com/signed"

        service.presign_get(key="k", expires_in=60)

        assert mock_client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 60

    def test_presign_get_wraps_client_error(self):
        service, mock_client = _service_with_mock_client()
        mock_client.generate_presigned_url.side_effect = _client_error("GetObject")

        with pytest.raises(StoragePresignError):
            service.presign_get(key="k")


class TestDelete:
    def test_delete_calls_boto3(self):
        service, mock_client = _service_with_mock_client()

        service.delete(key="evidence/org/res/file_a.pdf")

        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="evidence/org/res/file_a.pdf"
        )

    def test_delete_wraps_client_error(self):
        service, mock_client = _service_with_mock_client()
        mock_client.delete_object.side_effect = _client_error("DeleteObject")

        with pytest.raises(StorageDeleteError):
            service.delete(key="k")
