"""Password and JWT primitives; no global secrets, logging or network access."""

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import bcrypt
import jwt
from pydantic import BaseModel, ConfigDict, Field

Role = Literal["visualizador", "operador", "administrador"]
BCRYPT_COST = 11


class Claims(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sub: str
    role: Role
    jti: str
    auth_version: int = Field(ge=1)
    iss: str
    aud: str
    iat: int
    exp: int


def password_bytes(password: str, strong: bool = False) -> bytes:
    value = password.encode("utf-8")
    if (
        not (12 if strong else 1) <= len(value) <= 72
        or b"\0" in value
        or (strong and len(password) < 12)
    ):
        raise ValueError("Password length or encoding is invalid")
    return value


def hash_password(password: str, cost: int = BCRYPT_COST) -> bytes:
    return bcrypt.hashpw(
        password_bytes(password, strong=True), bcrypt.gensalt(rounds=cost)
    )


def check_password(password: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(password_bytes(password), hashed)
    except ValueError:
        return False


def keyed_identity(key: bytes, kind: str, value: str) -> str:
    return hmac.new(key, (kind + ":" + value).encode(), hashlib.sha256).hexdigest()


def decode_token(
    token: str,
    key: bytes,
    issuer: str = "smartfan-aiot",
    audience: str = "smartfan-web",
) -> Claims:
    if len(token) > 4096:
        raise ValueError("Token exceeds size limit")
    claims = Claims.model_validate(
        jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            leeway=30,
            options={
                "require": [
                    "sub",
                    "role",
                    "jti",
                    "auth_version",
                    "iss",
                    "aud",
                    "iat",
                    "exp",
                ],
                "strict_aud": True,
            },
        )
    )
    if (
        str(UUID(claims.sub)) != claims.sub
        or str(UUID(claims.jti)) != claims.jti
        or not 0 < claims.exp - claims.iat <= 1800
        or claims.iat > datetime.now(UTC).timestamp() + 30
    ):
        raise ValueError("Invalid session claims")
    return claims
