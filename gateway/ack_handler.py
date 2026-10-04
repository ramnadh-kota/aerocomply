"""Kota Aerospace - Safe Telemetry Acknowledgment and Error Classification Handler.

Evaluates upload HTTP responses and backend ingestion reports. Prevents poison batches
from blocking the queue, preserves valid telemetry during partial failures, and quarantines
permanently rejected records without leaking secrets.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("kota_gateway.ack")

_SECRET_PATTERN = re.compile(r"kdev\.[0-9a-fA-F-]+\.[A-Za-z0-9_-]+")


def mask_secret(text: str) -> str:
    """Mask sensitive device tokens in error messages and logs."""
    def _mask_match(m: re.Match[str]) -> str:
        parts = m.group(0).split(".")
        if len(parts) == 3:
            return f"{parts[0]}.{parts[1]}.***"
        return "kdev.***"

    return _SECRET_PATTERN.sub(_mask_match, str(text))


class AckAction(str, Enum):
    """Action to be taken on a queued batch based on upload response."""

    ACKNOWLEDGE = "ACKNOWLEDGE"      # Full success or duplicate-only: safely delete batch items
    RETRY = "RETRY"                  # Transient failure: retry batch with exponential backoff
    SPLIT = "SPLIT"                  # Partial acceptance or multi-item failure: split batch to isolate bad items
    QUARANTINE = "QUARANTINE"        # Permanent failure on single item: quarantine record with error reason
    PAUSE = "PAUSE"                  # Auth/perm failure (401/403/409): pause queue to avoid useless churn


@dataclass
class UploadEvaluation:
    """Evaluation result of an upload attempt."""

    action: AckAction
    status_code: int
    message: str
    accepted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    rejected: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    quarantine_reason: str | None = None
    is_transient: bool = False


class TelemetryAckHandler:
    """Evaluates telemetry upload responses to determine queue lifecycle actions."""

    def __init__(self, max_retries: int = 5) -> None:
        self.max_retries = max_retries

    def evaluate(
        self,
        status_code: int,
        response_body: dict[str, Any] | str | None,
        batch_size: int,
        attempt_count: int = 1,
    ) -> UploadEvaluation:
        """Classify upload result into actionable queue directives.

        Args:
            status_code: HTTP response code (200, 401, 403, 413, 500, etc., or 0 for network error)
            response_body: Decoded JSON dict or error text
            batch_size: Number of queued items in this batch
            attempt_count: Number of times this batch/item has been attempted
        """
        clean_msg = mask_secret(str(response_body))

        # ---------------------------------------------------------
        # 1. Success / Backend Ingestion Report (HTTP 200)
        # ---------------------------------------------------------
        if status_code == 200:
            if not isinstance(response_body, dict):
                # Malformed non-JSON 200 response
                logger.warning(f"Received HTTP 200 with non-JSON response: {clean_msg}")
                return UploadEvaluation(
                    action=AckAction.RETRY,
                    status_code=200,
                    message="Malformed HTTP 200 response body",
                    is_transient=True,
                )

            accepted = int(response_body.get("accepted", 0))
            duplicates = int(response_body.get("duplicates", 0))
            quarantined = int(response_body.get("quarantined", 0))
            rejected = int(response_body.get("rejected", 0))
            failed = int(response_body.get("failed", 0))
            raw_errors = response_body.get("errors", [])
            errors = [mask_secret(str(e)) for e in raw_errors] if isinstance(raw_errors, list) else []

            total_successful = accepted + duplicates
            total_unsuccessful = rejected + failed + (1 if errors and total_successful == 0 else 0)

            # Case A: Full Acceptance (no rejections, no failures, no backend errors)
            if accepted > 0 and rejected == 0 and failed == 0 and not errors:
                return UploadEvaluation(
                    action=AckAction.ACKNOWLEDGE,
                    status_code=200,
                    message=f"Batch accepted ({accepted} events)",
                    accepted=accepted,
                    duplicates=duplicates,
                )

            # Case B: Duplicate-Only Acceptance (idempotent re-send confirmed processed)
            if accepted == 0 and duplicates > 0 and rejected == 0 and failed == 0 and not errors:
                return UploadEvaluation(
                    action=AckAction.ACKNOWLEDGE,
                    status_code=200,
                    message=f"Batch duplicate-only acknowledged ({duplicates} duplicates)",
                    accepted=0,
                    duplicates=duplicates,
                )

            # Case C: Partial Acceptance (some frames accepted/duplicate, but some rejected/failed/errors)
            if total_successful > 0 and total_unsuccessful > 0:
                if batch_size > 1:
                    # In a multi-item batch, split so that valid records can be acknowledged
                    # and invalid records quarantined individually without guessing.
                    logger.warning(
                        f"Partial acceptance in multi-item batch (accepted={accepted}, dup={duplicates}, "
                        f"rejected={rejected}, errors={errors}). Splitting batch to isolate invalid records."
                    )
                    return UploadEvaluation(
                        action=AckAction.SPLIT,
                        status_code=200,
                        message="Partial acceptance: splitting batch",
                        accepted=accepted,
                        duplicates=duplicates,
                        rejected=rejected,
                        failed=failed,
                        errors=errors,
                    )
                else:
                    # Single item produced mixed results: valid frames were ingested
                    logger.info(
                        f"Single-item partial acceptance (accepted={accepted}, dup={duplicates}, rejected={rejected}). "
                        f"Acknowledging item since valid frames were persisted."
                    )
                    return UploadEvaluation(
                        action=AckAction.ACKNOWLEDGE,
                        status_code=200,
                        message="Single item accepted with partial frame rejections",
                        accepted=accepted,
                        duplicates=duplicates,
                        rejected=rejected,
                        errors=errors,
                    )

            # Case D: Full Rejection / Backend Ingestion Error (0 accepted, 0 duplicates)
            if total_successful == 0:
                error_summary = "; ".join(errors) if errors else f"Backend rejected all {rejected} frames"
                if batch_size > 1:
                    # Multi-item batch rejected: split to test individual items (avoids discarding good frames)
                    logger.warning(f"Batch rejected by backend ({error_summary}). Splitting batch into individual items.")
                    return UploadEvaluation(
                        action=AckAction.SPLIT,
                        status_code=200,
                        message=f"Full rejection: splitting batch ({error_summary})",
                        rejected=rejected,
                        failed=failed,
                        errors=errors,
                    )
                else:
                    # Single item permanently rejected by backend: quarantine it!
                    logger.error(f"Single item permanently rejected by backend: {error_summary}. Quarantining record.")
                    return UploadEvaluation(
                        action=AckAction.QUARANTINE,
                        status_code=200,
                        message=f"Quarantine: {error_summary}",
                        rejected=rejected,
                        failed=failed,
                        errors=errors,
                        quarantine_reason=error_summary,
                    )

            # Default fallback for 200
            return UploadEvaluation(
                action=AckAction.ACKNOWLEDGE,
                status_code=200,
                message="Batch processed",
                accepted=accepted,
                duplicates=duplicates,
            )

        # ---------------------------------------------------------
        # 2. Authentication & Authorization Errors (HTTP 401, 403)
        # ---------------------------------------------------------
        if status_code in (401, 403):
            logger.error(
                f"Permanent auth error (HTTP {status_code}): {clean_msg}. Pausing upload loop; not dropping telemetry."
            )
            return UploadEvaluation(
                action=AckAction.PAUSE,
                status_code=status_code,
                message=f"Auth error (HTTP {status_code}): {clean_msg}",
            )

        # ---------------------------------------------------------
        # 3. Missing Device Binding or Conflict (HTTP 409)
        # ---------------------------------------------------------
        if status_code == 409:
            logger.error(
                f"Configuration conflict (HTTP 409): {clean_msg}. Device requires data source binding by admin."
            )
            return UploadEvaluation(
                action=AckAction.PAUSE,
                status_code=409,
                message=f"Data source unbound (HTTP 409): {clean_msg}",
            )

        # ---------------------------------------------------------
        # 4. Payload Too Large (HTTP 413)
        # ---------------------------------------------------------
        if status_code == 413:
            if batch_size > 1:
                logger.warning(f"Batch exceeded server max payload size (HTTP 413). Splitting batch into smaller chunks.")
                return UploadEvaluation(
                    action=AckAction.SPLIT,
                    status_code=413,
                    message="Payload too large: splitting batch",
                )
            else:
                logger.error(f"Single record exceeds server upload size limit (HTTP 413). Quarantining oversized record.")
                return UploadEvaluation(
                    action=AckAction.QUARANTINE,
                    status_code=413,
                    message="Single record exceeds backend size limit (413)",
                    quarantine_reason="Payload size exceeds backend limit (HTTP 413)",
                )

        # ---------------------------------------------------------
        # 5. Unprocessable Entity (HTTP 422)
        # ---------------------------------------------------------
        if status_code == 422:
            if batch_size > 1:
                logger.warning(f"Unprocessable payload (HTTP 422): {clean_msg}. Splitting batch.")
                return UploadEvaluation(
                    action=AckAction.SPLIT,
                    status_code=422,
                    message="Unprocessable payload: splitting batch",
                )
            else:
                logger.error(f"Single record unprocessable by backend (HTTP 422): {clean_msg}. Quarantining.")
                return UploadEvaluation(
                    action=AckAction.QUARANTINE,
                    status_code=422,
                    message=f"Unprocessable record (HTTP 422): {clean_msg}",
                    quarantine_reason=f"Unprocessable entity (HTTP 422): {clean_msg}",
                )

        # ---------------------------------------------------------
        # 6. Rate Limiting (HTTP 429) & Server Errors (HTTP 5xx)
        # ---------------------------------------------------------
        if status_code in (429, 500, 502, 503, 504) or status_code == 0:
            if attempt_count >= self.max_retries and batch_size == 1:
                # Poison record or server error that has failed repeatedly
                quarantine_msg = f"Exceeded max retries ({attempt_count}) on HTTP {status_code}: {clean_msg}"
                logger.error(f"Quarantining item: {quarantine_msg}")
                return UploadEvaluation(
                    action=AckAction.QUARANTINE,
                    status_code=status_code,
                    message=quarantine_msg,
                    quarantine_reason=quarantine_msg,
                    is_transient=False,
                )
            elif attempt_count >= self.max_retries and batch_size > 1:
                return UploadEvaluation(
                    action=AckAction.SPLIT,
                    status_code=status_code,
                    message=f"Exceeded max retries ({attempt_count}): splitting batch",
                    is_transient=True,
                )
            else:
                return UploadEvaluation(
                    action=AckAction.RETRY,
                    status_code=status_code,
                    message=f"Transient failure (HTTP {status_code}): {clean_msg}",
                    is_transient=True,
                )

        # ---------------------------------------------------------
        # 7. Unhandled Status Code
        # ---------------------------------------------------------
        return UploadEvaluation(
            action=AckAction.RETRY,
            status_code=status_code,
            message=f"Unexpected status code {status_code}: {clean_msg}",
            is_transient=True,
        )
