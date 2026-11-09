import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from services.api.main import Login, UserCreate
from services.api.security import (
    check_password,
    decode_token,
    hash_password,
    password_bytes,
)


def test_bcrypt_rejects_truncation_unicode_and_nul():
    hashed = hash_password("test-only-valid-password", cost=4)
    assert check_password("test-only-valid-password", hashed)
    assert not check_password("test-only-wrong-password", hashed)
    for value in ("a" * 73, "á" * 37, "abc\0defghijklmnop"):
        with pytest.raises(ValueError):
            password_bytes(value, strong=True)
        assert not check_password(value, hashed)


def test_jwt_claims_algorithm_issuer_audience_and_expiration():
    key = secrets.token_bytes(64)
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid4()),
        "jti": str(uuid4()),
        "role": "visualizador",
        "auth_version": 1,
        "iss": "smartfan-aiot",
        "aud": "smartfan-web",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    token = jwt.encode(claims, key, algorithm="HS256")
    assert decode_token(token, key).role == "visualizador"
    for update in (
        {"aud": "other"},
        {"iss": "other"},
        {"exp": int(now.timestamp()) - 31},
        {"auth_version": True},
        {"role": "root"},
        {"iat": int(now.timestamp()) + 60},
    ):
        with pytest.raises((jwt.PyJWTError, ValueError)):
            decode_token(jwt.encode({**claims, **update}, key, algorithm="HS256"), key)
    with pytest.raises((jwt.PyJWTError, ValueError)):
        decode_token(jwt.encode(claims, key, algorithm="HS384"), key)


def test_request_password_is_secret_and_user_creation_is_strict():
    body = Login.model_validate(
        {"username": "test", "password": "test-only-valid-password"}
    )
    assert "test-only-valid-password" not in repr(body)
    with pytest.raises(ValueError):
        UserCreate.model_validate(
            {"username": "test", "password": "short", "role": "operador"}
        )
    assert (
        UserCreate.model_validate(
            {
                "username": "TEST",
                "password": "test-only-valid-password",
                "role": "operador",
            }
        ).username
        == "test"
    )
