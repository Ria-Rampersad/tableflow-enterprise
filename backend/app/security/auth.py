"""Authentication and authorisation.

Three ways a caller can prove who they are:

1. **Users (people)** - OAuth 2.0 *password* grant at `/api/v1/auth/login`. The
   password is checked against a bcrypt hash and a signed JWT is issued.
2. **Machine clients (n8n, finance system)** - OAuth 2.0 *client-credentials*
   grant at `/api/v1/auth/token`. Returns a JWT carrying scopes.
3. **Digital-ordering partners (Uber Eats, Mr D)** - static API key in the
   `X-API-Key` header, compared in constant time.

Authorisation is role-based (RBAC): each endpoint declares the roles or scopes
it accepts via `require_roles(...)`.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

ROLES = ("admin", "finance", "operations", "branch_manager", "integration_engineer")
# Machine-client scopes map onto the same permission model as roles.
SCOPE_TO_ROLE = {
    "automation:run": "operations",
    "reports:read": "finance",
    "integrations:manage": "integration_engineer",
}


# ---------------------------------------------------------------- passwords
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


# ---------------------------------------------------------------- JWT
def create_access_token(subject: str, roles: list[str], token_type: str = "user", extra: dict | None = None) -> str:  # noqa: S107 - "user" is a claim type, not a password
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "roles": roles,
        "typ": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_expire_minutes),
        "iss": "tableflow-enterprise",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm], issuer="tableflow-enterprise")
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired", {"WWW-Authenticate": "Bearer"}) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token", {"WWW-Authenticate": "Bearer"}) from exc


@dataclass
class Principal:
    """Whoever is calling: a human user or a machine client."""

    subject: str
    roles: list[str] = field(default_factory=list)
    kind: str = "user"  # user | client
    user_id: int | None = None
    branch_id: int | None = None

    def has_any(self, *roles: str) -> bool:
        return "admin" in self.roles or any(r in self.roles for r in roles)


def get_current_principal(
    request: Request, token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Principal:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", {"WWW-Authenticate": "Bearer"})
    claims = decode_token(token)
    if claims.get("typ") == "client":
        roles = sorted({SCOPE_TO_ROLE[s] for s in claims.get("scopes", []) if s in SCOPE_TO_ROLE})
        principal = Principal(subject=claims["sub"], roles=roles, kind="client")
    else:
        user = db.get(User, int(claims["sub"]))
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
        principal = Principal(
            subject=user.email, roles=[user.role.name], kind="user", user_id=user.id, branch_id=user.branch_id
        )
    request.state.principal = principal
    return principal


def require_roles(*roles: str):
    """Dependency factory: `Depends(require_roles("finance"))`. Admin always passes."""

    def checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if roles and not principal.has_any(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires one of roles: {', '.join(roles)}")
        return principal

    return checker


# ---------------------------------------------------------------- partner API keys
def require_partner_key(provider: str):
    """Validate the `X-API-Key` header for a digital-ordering partner."""

    def checker(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
        expected = get_settings().partner_keys.get(provider)
        if not x_api_key or not expected or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")
        return provider

    return checker
