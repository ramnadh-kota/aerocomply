"""Pure helpers for building tenant-safe object storage keys.

No I/O, no boto3 dependency — independently unit-testable. Every path
segment except the trailing filename is a server-generated UUID
(organization_id, resource_id, file_id), so a client can never influence the
directory structure of an object key; the filename itself is sanitized to a
single safe path segment before use.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

_MAX_FILENAME_LENGTH = 200
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_NAMESPACE_RE = re.compile(r"^[a-z0-9_-]+$")
_DEFAULT_FALLBACK_FILENAME = "file"


def sanitize_filename(filename: str, *, fallback: str = _DEFAULT_FALLBACK_FILENAME) -> str:
    """Return a safe, single-path-segment filename for use in an object key.

    Never trust the result for authorization — it only guarantees the
    filename cannot escape its own path segment (no '/', '\\', or '..'
    traversal) and cannot contain control characters or an unbounded length.
    Unicode and spaces are preserved where safe, since the filename is only
    ever used for the human-readable tail of an object key and (later) for
    Content-Disposition, never to look anything up.
    """
    if not filename:
        return fallback

    name = unicodedata.normalize("NFC", filename)
    name = _CONTROL_CHARS_RE.sub("", name)

    # Defeat path traversal / absolute paths by keeping only the final
    # segment, regardless of which separator style was used.
    name = name.replace("\\", "/")
    name = name.split("/")[-1]

    name = name.strip().strip(".")
    if not name or name in {".", ".."}:
        return fallback

    if len(name) > _MAX_FILENAME_LENGTH:
        base, dot, ext = name.rpartition(".")
        if dot and base and 0 < len(ext) <= 20:
            keep = _MAX_FILENAME_LENGTH - len(ext) - 1
            name = f"{base[:keep]}.{ext}" if keep > 0 else name[:_MAX_FILENAME_LENGTH]
        else:
            name = name[:_MAX_FILENAME_LENGTH]

    return name or fallback


def build_object_key(
    *,
    namespace: str,
    organization_id: uuid.UUID,
    resource_id: uuid.UUID,
    file_id: uuid.UUID,
    filename: str,
) -> str:
    """Build a deterministic, tenant-scoped object key.

    Shape: {namespace}/{organization_id}/{resource_id}/{file_id}_{filename}

    `namespace` distinguishes callers of this shared helper (e.g. "evidence"
    today; a future "regulatory-document" caller could reuse it) without
    coupling this module to any specific domain model. organization_id,
    resource_id, and file_id must always be server-generated UUIDs — never
    accept these as raw client-supplied strings, or the tenant-isolation
    guarantee of this key structure is void.
    """
    if not _NAMESPACE_RE.fullmatch(namespace):
        raise ValueError(
            f"namespace must match {_NAMESPACE_RE.pattern!r} (got {namespace!r})"
        )

    safe_filename = sanitize_filename(filename)
    return f"{namespace}/{organization_id}/{resource_id}/{file_id}_{safe_filename}"


__all__ = ["sanitize_filename", "build_object_key"]
