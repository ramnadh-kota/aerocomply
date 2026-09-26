import uuid

import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hash_is_not_plaintext():
    hashed = hash_password("secret")
    assert hashed != "secret"


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    token = create_access_token(user_id, org_id, ["VIEWER"])
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["organization_id"] == str(org_id)
    assert payload["roles"] == ["VIEWER"]
    assert payload["type"] == "access"


def test_invalid_token_raises():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-valid-jwt")


def test_update_profile_request_schema():
    from pydantic import ValidationError
    from app.schemas.auth import UpdateProfileRequest

    valid = UpdateProfileRequest(full_name="Captain Ramnadh")
    assert valid.full_name == "Captain Ramnadh"

    with pytest.raises(ValidationError):
        UpdateProfileRequest(full_name="")

    none_ok = UpdateProfileRequest(full_name=None)
    assert none_ok.full_name is None


def test_update_user_profile_not_found_raises():
    from unittest.mock import MagicMock
    from app.core.errors import NotFoundError
    from app.services.auth_service import update_user_profile

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(NotFoundError):
        update_user_profile(mock_db, user_id=uuid.uuid4(), full_name="New Name")

