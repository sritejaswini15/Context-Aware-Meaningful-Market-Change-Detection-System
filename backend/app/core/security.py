"""Password hashing, local JWTs and Cognito token verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.core.config import get_settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$", 2)
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    actual = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return hmac.compare_digest(actual, expected)


@dataclass
class TokenClaims:
    subject: str  # local: user id; cognito: sub
    email: str | None
    provider: str  # local | cognito


class AuthError(Exception):
    pass


def issue_local_token(user_id: str, email: str) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {"sub": user_id, "email": email, "iat": now, "exp": now + s.jwt_ttl_minutes * 60, "iss": "knoww", "typ": "access"}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def _verify_local(token: str) -> TokenClaims:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], issuer="knoww")
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    return TokenClaims(subject=data["sub"], email=data.get("email"), provider="local")


@lru_cache(maxsize=1)
def _cognito_jwks() -> jwt.PyJWKClient:
    s = get_settings()
    url = f"https://cognito-idp.{s.cognito_region}.amazonaws.com/{s.cognito_user_pool_id}/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def _verify_cognito(token: str) -> TokenClaims:
    s = get_settings()
    issuer = f"https://cognito-idp.{s.cognito_region}.amazonaws.com/{s.cognito_user_pool_id}"
    try:
        key = _cognito_jwks().get_signing_key_from_jwt(token)
        data = jwt.decode(token, key.key, algorithms=["RS256"], issuer=issuer, options={"verify_aud": False})
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    # ID tokens carry `aud`; access tokens carry `client_id`.
    if data.get("token_use") == "id":
        if data.get("aud") != s.cognito_client_id:
            raise AuthError("Token audience mismatch")
    elif data.get("token_use") == "access":
        if data.get("client_id") != s.cognito_client_id:
            raise AuthError("Token client mismatch")
    else:
        raise AuthError("Unsupported token use")
    return TokenClaims(subject=data["sub"], email=data.get("email"), provider="cognito")


def verify_token(token: str) -> TokenClaims:
    if get_settings().auth_mode == "cognito":
        return _verify_cognito(token)
    return _verify_local(token)
