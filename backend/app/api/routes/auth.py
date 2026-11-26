from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import REFRESH_COOKIE, SESSION_COOKIE, get_current_user, rate_limit
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import Unauthorized
from app.models import User
from app.schemas.api import AuthOut, ConfirmIn, LoginIn, OnboardingIn, ProfilePatch, SignupIn, UserOut
from app.services.preferences.service import update_preferences
from app.services.users import service as auth
from app.services.watchlists.service import create_watchlist, list_watchlists

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, email=u.email, display_name=u.display_name, onboarded=u.onboarded_at is not None, auth_provider=u.auth_provider, created_at=u.created_at
    )


def _set_session(response: Response, token: str, refresh: str | None = None, expires_in: int | None = None) -> None:
    s = get_settings()
    max_age = expires_in or s.jwt_ttl_minutes * 60
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain, path="/")
    if refresh:
        response.set_cookie(
            REFRESH_COOKIE, refresh, max_age=30 * 86400, httponly=True, secure=s.cookie_secure, samesite="strict", domain=s.cookie_domain, path="/api/auth"
        )


@router.post("/signup", response_model=AuthOut, dependencies=[Depends(rate_limit("auth", 20))])
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    result = auth.signup(db, body.email, body.password, body.display_name)
    db.commit()
    if result.token:
        _set_session(response, result.token)
    return AuthOut(status=result.status, user=user_out(result.user) if result.user else None, token=result.token)


@router.post("/confirm", dependencies=[Depends(rate_limit("auth", 20))])
def confirm(body: ConfirmIn, db: Session = Depends(get_db)):
    auth.confirm(db, body.email, body.code)
    return {"status": "CONFIRMED"}


@router.post("/login", response_model=AuthOut, dependencies=[Depends(rate_limit("auth", 20))])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    result = auth.login(db, body.email, body.password)
    result.user.last_seen_at = datetime.now(UTC)
    db.commit()
    _set_session(response, result.token, result.refresh_token, result.expires_in)
    return AuthOut(status="OK", user=user_out(result.user), token=result.token)


@router.post("/refresh", response_model=AuthOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise Unauthorized("No refresh session")
    result = auth.refresh(db, token)
    _set_session(response, result.token, None, result.expires_in)
    return AuthOut(status="OK", token=result.token)


@router.post("/logout")
def logout(response: Response):
    s = get_settings()
    response.delete_cookie(SESSION_COOKIE, path="/", domain=s.cookie_domain)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", domain=s.cookie_domain)
    return {"status": "OK"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.commit()
    return user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfilePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
    db.commit()
    return user_out(user)


onboarding = APIRouter(tags=["auth"])


@onboarding.post("/onboarding", response_model=UserOut)
def complete_onboarding(body: OnboardingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Step 2-4 of onboarding in one call: first watchlist + sensitivity."""
    if not list_watchlists(db, user):
        create_watchlist(db, user, body.watchlist_name.strip(), body.symbols)
    update_preferences(db, user, {"sensitivity": body.sensitivity})
    user.onboarded_at = user.onboarded_at or datetime.now(UTC)
    db.commit()
    return user_out(user)
