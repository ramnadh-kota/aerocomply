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
