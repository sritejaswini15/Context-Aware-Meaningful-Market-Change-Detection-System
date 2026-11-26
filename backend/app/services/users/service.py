"""Authentication. Local mode issues its own JWTs; Cognito mode delegates
credentials to Amazon Cognito (USER_PASSWORD_AUTH) and verifies Cognito JWTs.
The frontend is identical in both modes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, DomainError, Unauthorized
from app.core.logging import log_event
from app.core.security import TokenClaims, hash_password, issue_local_token, verify_password
from app.models import User, UserPreferences


@dataclass
class AuthResult:
    status: str
    user: User | None = None
    token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None


def _cognito():
    import boto3

    return boto3.client("cognito-idp", region_name=get_settings().cognito_region)


def _get_or_create(db: Session, email: str, provider: str, external_id: str | None = None, display_name: str | None = None) -> User:
    user = None
    if external_id:
        user = db.scalar(select(User).where(User.external_id == external_id))
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is None:
        user = User(email=email.lower(), auth_provider=provider, external_id=external_id, display_name=display_name)
        db.add(user)
        db.flush()
        db.add(UserPreferences(user_id=user.id))
        db.flush()
        log_event("user.created", user_id=str(user.id), provider=provider)
    elif external_id and not user.external_id:
        user.external_id = external_id
    return user


def signup(db: Session, email: str, password: str, display_name: str | None) -> AuthResult:
    s = get_settings()
    email = email.lower()
    if s.auth_mode == "cognito":
        client = _cognito()
        try:
            client.sign_up(ClientId=s.cognito_client_id, Username=email, Password=password, UserAttributes=[{"Name": "email", "Value": email}])
        except client.exceptions.UsernameExistsException as exc:
            raise Conflict("An account with this email already exists") from exc
        except client.exceptions.InvalidPasswordException as exc:
            raise DomainError(str(exc.response["Error"]["Message"]), "weak_password") from exc
        user = _get_or_create(db, email, "cognito", display_name=display_name)
        return AuthResult(status="CONFIRMATION_REQUIRED", user=user)
    if db.scalar(select(User).where(func.lower(User.email) == email)) is not None:
        raise Conflict("An account with this email already exists")
    user = _get_or_create(db, email, "local", display_name=display_name)
    user.password_hash = hash_password(password)
    return AuthResult(status="OK", user=user, token=issue_local_token(str(user.id), user.email))


def confirm(db: Session, email: str, code: str) -> None:
    s = get_settings()
    if s.auth_mode != "cognito":
        return
    client = _cognito()
    try:
        client.confirm_sign_up(ClientId=s.cognito_client_id, Username=email.lower(), ConfirmationCode=code)
    except (client.exceptions.CodeMismatchException, client.exceptions.ExpiredCodeException) as exc:
        raise DomainError("Invalid or expired confirmation code", "invalid_code") from exc


def login(db: Session, email: str, password: str) -> AuthResult:
    s = get_settings()
    email = email.lower()
    if s.auth_mode == "cognito":
        client = _cognito()
        try:
            resp = client.initiate_auth(
                ClientId=s.cognito_client_id, AuthFlow="USER_PASSWORD_AUTH", AuthParameters={"USERNAME": email, "PASSWORD": password}
            )
        except client.exceptions.UserNotConfirmedException as exc:
            raise DomainError("Please confirm your email first", "not_confirmed") from exc
        except (client.exceptions.NotAuthorizedException, client.exceptions.UserNotFoundException) as exc:
            raise Unauthorized("Incorrect email or password") from exc
        auth = resp["AuthenticationResult"]
        from app.core.security import verify_token

        claims = verify_token(auth["IdToken"])
        user = _get_or_create(db, claims.email or email, "cognito", external_id=claims.subject)
        return AuthResult("OK", user, auth["IdToken"], auth.get("RefreshToken"), auth.get("ExpiresIn"))
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(password, user.password_hash):
        log_event("auth.login_failed", email_domain=email.split("@")[-1])
        raise Unauthorized("Incorrect email or password")
    return AuthResult("OK", user, issue_local_token(str(user.id), user.email))


def refresh(db: Session, refresh_token: str) -> AuthResult:
    s = get_settings()
    if s.auth_mode != "cognito":
        raise Unauthorized("Refresh not supported in local mode")
    client = _cognito()
    try:
        resp = client.initiate_auth(ClientId=s.cognito_client_id, AuthFlow="REFRESH_TOKEN_AUTH", AuthParameters={"REFRESH_TOKEN": refresh_token})
    except client.exceptions.NotAuthorizedException as exc:
        raise Unauthorized("Session expired") from exc
    auth = resp["AuthenticationResult"]
    return AuthResult("OK", None, auth["IdToken"], None, auth.get("ExpiresIn"))


def user_from_claims(db: Session, claims: TokenClaims) -> User | None:
    import uuid

    if claims.provider == "local":
        try:
            return db.get(User, uuid.UUID(claims.subject))
        except ValueError:
            return None
    user = db.scalar(select(User).where(User.external_id == claims.subject))
    if user is None and claims.email:
        user = _get_or_create(db, claims.email, "cognito", external_id=claims.subject)
    return user


def touch(user: User) -> None:
    now = datetime.now(UTC)
    if user.last_seen_at is None or (now - user.last_seen_at).total_seconds() > 300:
        user.last_seen_at = now
