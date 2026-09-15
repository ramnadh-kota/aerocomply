"""Storage-layer exception hierarchy.

Deliberately independent of app.core.errors.AeroComplyError — these are not
yet mapped to any HTTP status code. A future API layer (the evidence-file
upload/download endpoints) will decide how each of these should surface to a
client; this module only hides raw boto3/botocore exceptions from callers so
the rest of the application never needs to import botocore.
"""


class StorageError(Exception):
    """Base class for all storage-layer failures. Never raised directly."""


class StorageNotConfiguredError(StorageError):
    """Raised when a storage operation is attempted without required configuration."""


class StorageUploadError(StorageError):
    """Raised when uploading an object to the backing store fails."""


class StorageDeleteError(StorageError):
    """Raised when deleting an object from the backing store fails."""


class StoragePresignError(StorageError):
    """Raised when generating a presigned URL for an object fails."""


class StorageUnavailableError(StorageError):
    """Raised by an existence check (M16.8 reconciliation) when the backing
    store could not definitively answer whether an object exists --
    permission denied, timeout, provider/network failure, or any other
    ambiguous response. Deliberately distinct from a normal "the object does
    not exist" result (which is not an error at all -- see
    StorageService.object_exists returning False): callers must never treat
    this exception as proof of absence, only as "unknown, try again later."
    """


__all__ = [
    "StorageError",
    "StorageNotConfiguredError",
    "StorageUploadError",
    "StorageDeleteError",
    "StoragePresignError",
    "StorageUnavailableError",
]
