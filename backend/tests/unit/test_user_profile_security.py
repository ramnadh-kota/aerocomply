import uuid
from unittest.mock import MagicMock, patch
import pytest

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.user import User
from app.models.auth_verification import VerificationPurpose
from app.schemas.auth import (
    ConfirmEmailChangeRequest,
    RequestEmailChangeRequest,
    UpdateProfileRequest,
)
from app.services.auth_service import (
    cancel_email_change,
    confirm_email_change,
    delete_profile_photo,
    request_email_change,
    update_user_profile,
    upload_profile_photo,
)


def _make_mock_user(
    *,
    user_id: uuid.UUID | None = None,
    email: str = "pilot@aerocomply.com",
    full_name: str = "Captain Vikram",
    phone_number: str | None = None,
    profile_photo_url: str | None = None,
    pending_email: str | None = None,
) -> User:
    user = User(
        id=user_id or uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email=email,
        hashed_password="fakehashnotplaintext",
        full_name=full_name,
        phone_number=phone_number,
        profile_photo_url=profile_photo_url,
        pending_email=pending_email,
        email_verified=True,
    )
    return user


def test_update_profile_phone_schema():
    valid = UpdateProfileRequest(phone_number="+91 98765 43210")
    assert valid.phone_number == "+91 98765 43210"

    none_phone = UpdateProfileRequest(phone_number=None)
    assert none_phone.phone_number is None


def test_update_profile_phone_format_validation():
    mock_db = MagicMock()
    user = _make_mock_user()
    mock_db.execute.return_value.scalar_one_or_none.return_value = user

    # Invalid phone format
    with pytest.raises(AeroComplyError) as exc_info:
        update_user_profile(mock_db, user_id=user.id, phone_number="not-a-number")
    assert exc_info.value.code == "invalid_phone_number"

    # Valid phone formats
    for valid_phone in ["+91 9876543210", "+1 (555) 123-4567", "044-2234-5678", "+44 20 7946 0991"]:
        with patch("app.services.auth_service.record_audit_event") as mock_audit, \
             patch("app.services.auth_service._roles_for_user", return_value=["VIEWER"]):
            result = update_user_profile(mock_db, user_id=user.id, phone_number=valid_phone)
            assert user.phone_number == valid_phone
            assert result.phone_number == valid_phone
            mock_audit.assert_called_once()


def test_upload_profile_photo_mime_validation():
    mock_db = MagicMock()
    user = _make_mock_user()
    mock_db.get.return_value = user

    # Rejected mime type
    with pytest.raises(AeroComplyError) as exc_info:
        upload_profile_photo(
            mock_db,
            user_id=user.id,
            content=b"executable binary",
            content_type="application/x-executable",
            filename="malware.exe",
        )
    assert exc_info.value.code == "unsupported_image_format"

    # Rejected oversized file (>2MB)
    oversized = b"0" * (2 * 1024 * 1024 + 10)
    with pytest.raises(AeroComplyError) as exc_info:
        upload_profile_photo(
            mock_db,
            user_id=user.id,
            content=oversized,
            content_type="image/jpeg",
            filename="giant.jpg",
        )
    assert exc_info.value.code == "photo_too_large"


def test_upload_profile_photo_success_and_delete():
    mock_db = MagicMock()
    user = _make_mock_user()
    mock_db.get.return_value = user

    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with patch("app.services.auth_service.record_audit_event") as mock_audit, \
         patch("app.services.auth_service._roles_for_user", return_value=["ADMIN"]):
        res = upload_profile_photo(
            mock_db,
            user_id=user.id,
            content=tiny_png,
            content_type="image/png",
            filename="avatar.png",
        )
        assert res.profile_photo_url is not None
        assert user.profile_photo_url.startswith("data:image/png;base64,")
        mock_audit.assert_called_once()

    # Now delete photo
    with patch("app.services.auth_service.record_audit_event") as mock_audit, \
         patch("app.services.auth_service._roles_for_user", return_value=["ADMIN"]):
        del_res = delete_profile_photo(mock_db, user_id=user.id)
        assert del_res.profile_photo_url is None
        assert user.profile_photo_url is None
        mock_audit.assert_called_once()


def test_request_email_change_validations():
    mock_db = MagicMock()
    user = _make_mock_user(email="current@aerocomply.com")
    mock_db.get.return_value = user

    # Requesting exact same email
    with pytest.raises(ConflictError) as exc_info:
        request_email_change(mock_db, user_id=user.id, new_email="current@aerocomply.com")
    assert exc_info.value.code == "identical_email"

    # Requesting email taken by another user
    other_user = _make_mock_user(email="taken@aerocomply.com")
    mock_db.execute.return_value.scalar_one_or_none.return_value = other_user
    with pytest.raises(ConflictError) as exc_info:
        request_email_change(mock_db, user_id=user.id, new_email="taken@aerocomply.com")
    assert exc_info.value.code == "email_in_use"


def test_email_change_full_workflow():
    mock_db = MagicMock()
    user = _make_mock_user(email="old@aerocomply.com")
    mock_db.get.return_value = user
    # No collision
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    with patch("app.services.auth_service._issue_code", return_value="654321") as mock_issue, \
         patch("app.services.auth_service.send_verification_code_email") as mock_send, \
         patch("app.services.auth_service.record_audit_event") as mock_audit:
        request_email_change(mock_db, user_id=user.id, new_email="new@aerocomply.com")
        assert user.pending_email == "new@aerocomply.com"
        assert user.email == "old@aerocomply.com"  # Active email remains unchanged!
        mock_issue.assert_called_once()
        mock_send.assert_called_once()

    # Confirm email change with correct OTP
    with patch("app.services.auth_service._consume_code") as mock_consume, \
         patch("app.services.auth_service.record_audit_event") as mock_audit, \
         patch("app.services.auth_service._roles_for_user", return_value=["ADMIN"]):
        confirmed_user = confirm_email_change(mock_db, user_id=user.id, code="654321")
        assert user.email == "new@aerocomply.com"
        assert user.pending_email is None
        assert user.email_verified is True
        mock_consume.assert_called_once()
        mock_audit.assert_called_once()


def test_cancel_email_change():
    mock_db = MagicMock()
    user = _make_mock_user(email="active@aerocomply.com", pending_email="in_flight@aerocomply.com")
    mock_db.get.return_value = user

    with patch("app.services.auth_service.record_audit_event") as mock_audit, \
         patch("app.services.auth_service._roles_for_user", return_value=["VIEWER"]):
        cancelled = cancel_email_change(mock_db, user_id=user.id)
        assert user.pending_email is None
        assert user.email == "active@aerocomply.com"
        mock_audit.assert_called_once()
