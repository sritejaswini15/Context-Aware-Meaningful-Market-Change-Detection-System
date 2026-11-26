from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.db import get_db
from app.core.errors import RateLimited, Unauthorized
from app.core.security import AuthError, verify_token
from app.models import User
from app.services.users.service import touch, user_from_claims

SESSION_COOKIE = "knoww_session"
REFRESH_COOKIE = "knoww_refresh"


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token(request)
    if not token:
        raise Unauthorized("Sign in required")
    try:
        claims = verify_token(token)
    except AuthError as exc:
        raise Unauthorized("Session expired or invalid") from exc
    user = user_from_claims(db, claims)
    if user is None:
        raise Unauthorized("Account not found")
    touch(user)
    request.state.user_id = str(user.id)
    _limit(f"user:{user.id}", limit=600, window=60)
    return user


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def _limit(key: str, limit: int, window: int) -> None:
    count = get_cache().incr(f"rl:{key}:{window}", window)
    if count > limit:
        raise RateLimited("Too many requests. Please slow down.")


def rate_limit(scope: str, limit: int, window: int = 60) -> Callable[[Request], None]:
    def dep(request: Request) -> None:
        _limit(f"{scope}:{client_ip(request)}", limit, window)

    return dep
