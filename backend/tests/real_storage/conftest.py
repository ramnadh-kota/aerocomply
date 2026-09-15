"""Fixtures for M17.1 real-storage tests.

db_session/engine are reused verbatim from tests/integration/conftest.py
(same real-Alembic-migration, transaction-per-test-rollback fixtures) --
this module never duplicates that logic, only imports it, so both suites
stay behind one single source of truth for how the test database is set up.

storage_service is new here: a real StorageService instance pointed at
whatever S3-compatible endpoint the environment configures (see
tests/real_storage/README.md), NOT the app's own get_storage_service()
singleton/settings (so a developer's normal .env / dev MinIO settings are
never silently reused for a destructive test bucket).
"""

import os

import boto3
import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.services.storage.service import StorageService
from tests.integration.conftest import client, db_session, engine  # noqa: F401


def _real_storage_settings() -> Settings | None:
    endpoint_url = os.environ.get("REAL_STORAGE_S3_ENDPOINT_URL")
    if not endpoint_url:
        return None
    return Settings(
        database_url="sqlite://",  # unused by StorageService; Settings requires a value
        jwt_secret_key="test-only",
        s3_endpoint_url=endpoint_url,
        s3_access_key=os.environ.get("REAL_STORAGE_S3_ACCESS_KEY", "aerocomply"),
        s3_secret_key=os.environ.get("REAL_STORAGE_S3_SECRET_KEY", "aerocomply_dev_secret"),
        s3_bucket=os.environ.get("REAL_STORAGE_S3_BUCKET", "aerocomply-evidence-test"),
        s3_region=os.environ.get("REAL_STORAGE_S3_REGION", "us-east-1"),
        s3_force_path_style=os.environ.get("REAL_STORAGE_S3_FORCE_PATH_STYLE", "true").lower()
        != "false",
        s3_presigned_url_expire_seconds=int(
            os.environ.get("REAL_STORAGE_S3_PRESIGNED_EXPIRE_SECONDS", "300")
        ),
    )


@pytest.fixture(scope="session")
def real_storage_settings() -> Settings:
    settings = _real_storage_settings()
    if settings is None:
        pytest.skip(
            "REAL_STORAGE_S3_ENDPOINT_URL is not set -- see tests/real_storage/README.md "
            "for how to start a real S3-compatible endpoint and point tests at it."
        )
    return settings


@pytest.fixture(scope="session")
def _ensure_test_bucket(real_storage_settings: Settings) -> None:
    """Create the test bucket if it doesn't already exist. Session-scoped and
    idempotent -- never deletes the bucket itself (see the README for manual
    teardown of the throwaway local server/data dir instead)."""
    s3_client = boto3.client(
        "s3",
        endpoint_url=real_storage_settings.s3_endpoint_url,
        aws_access_key_id=real_storage_settings.s3_access_key,
        aws_secret_access_key=real_storage_settings.s3_secret_key,
        region_name=real_storage_settings.s3_region,
    )
    try:
        s3_client.head_bucket(Bucket=real_storage_settings.s3_bucket)
    except ClientError:
        s3_client.create_bucket(Bucket=real_storage_settings.s3_bucket)


@pytest.fixture
def storage_service(real_storage_settings: Settings, _ensure_test_bucket: None) -> StorageService:
    """A real StorageService talking to a real S3-compatible HTTP endpoint --
    never a mock, never a StorageService double. See the module docstring."""
    return StorageService(real_storage_settings)
