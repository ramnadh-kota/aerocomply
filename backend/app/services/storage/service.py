"""S3-compatible object storage abstraction.

Hides boto3/botocore wire details from the rest of the application — callers
only ever see StorageService's put/presign_get/delete methods and the
exception hierarchy in app.services.storage.exceptions, never a raw boto3
client or botocore exception. This keeps future callers (e.g. an
EvidenceFile upload endpoint added in a later milestone) agnostic to whether
the backing store is AWS S3 in production or a local MinIO instance in
development — both are the same S3-compatible wire protocol, distinguished
only by configuration (see app.core.config: s3_endpoint_url,
s3_force_path_style).

Synchronous, matching the rest of this backend's architecture (SQLAlchemy
Session-based services, no async DB/service layer).

Constructing a StorageService never performs network I/O or validates
credentials (boto3.client() only builds a local client object), so this is
safe to construct even when the configured S3 credentials are the local-dev
placeholder defaults — the app must be able to start without real S3 access.
An actual put/presign_get/delete call will fail clearly (raising one of this
module's exceptions) if the configuration is genuinely incomplete or wrong,
the same honest-failure principle already used by get_ai_provider() /
NotConfiguredProvider for the Lisa AI integration. This module never falls
back to local filesystem storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.storage.exceptions import (
    StorageDeleteError,
    StorageNotConfiguredError,
    StoragePresignError,
    StorageUnavailableError,
    StorageUploadError,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class PutResult:
    """Result of a successful upload."""

    key: str
    size_bytes: int


class StorageService:
    """Synchronous S3-compatible storage client wrapper.

    Prefer get_storage_service() over constructing this directly, so the
    process shares one client rather than opening a new one per call.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.s3_bucket:
            raise StorageNotConfiguredError("S3_BUCKET is not configured.")
        self._bucket = settings.s3_bucket
        self._default_expires_in = settings.s3_presigned_url_expire_seconds
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"}
            ),
        )

    def put(self, *, key: str, body: bytes, content_type: str) -> PutResult:
        """Upload `body` to `key`. Raises StorageUploadError on failure."""
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=body, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as exc:
            logger.warning("storage_put_failed", key=key, error=str(exc))
            raise StorageUploadError(f"Failed to upload object {key!r}: {exc}") from exc
        return PutResult(key=key, size_bytes=len(body))

    def presign_get(self, *, key: str, expires_in: int | None = None) -> str:
        """Return a time-limited GET URL for `key`. Raises StoragePresignError on failure."""
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in if expires_in is not None else self._default_expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.warning("storage_presign_failed", key=key, error=str(exc))
            raise StoragePresignError(
                f"Failed to generate a presigned URL for {key!r}: {exc}"
            ) from exc

    def object_exists(self, *, key: str) -> bool:
        """Return True if `key` exists, False if it definitively does not.

        Used only by M16.8 reconciliation to compare recorded EvidenceFile
        metadata against real object-storage state. This is a HEAD request
        (no body transfer) -- it never downloads content and never returns a
        presigned URL.

        Critically, this method distinguishes "does not exist" from
        "could not determine": a 404/NoSuchKey response is the only case
        that returns False. Anything else -- wrong credentials, a timeout, a
        provider/network failure, or any other ambiguous error -- raises
        StorageUnavailableError instead. Callers (reconciliation) must never
        treat that exception as proof the object is missing.
        """
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            error_code = exc.response.get("Error", {}).get("Code", "")
            if status_code == 404 or error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            logger.warning("storage_object_exists_check_failed", key=key, error=str(exc))
            raise StorageUnavailableError(
                f"Could not determine whether object {key!r} exists: {exc}"
            ) from exc
        except BotoCoreError as exc:
            logger.warning("storage_object_exists_check_failed", key=key, error=str(exc))
            raise StorageUnavailableError(
                f"Could not determine whether object {key!r} exists: {exc}"
            ) from exc
        return True

    def delete(self, *, key: str) -> None:
        """Delete `key`. Raises StorageDeleteError on failure."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("storage_delete_failed", key=key, error=str(exc))
            raise StorageDeleteError(f"Failed to delete object {key!r}: {exc}") from exc


@lru_cache
def get_storage_service() -> StorageService:
    """Factory returning the process-wide StorageService instance."""
    return StorageService(get_settings())


__all__ = ["StorageService", "PutResult", "get_storage_service"]
