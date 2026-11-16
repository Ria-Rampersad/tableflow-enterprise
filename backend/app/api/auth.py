"""Authentication endpoints (OAuth 2.0 password + client-credentials grants) and user admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip
from app.config import get_settings
from app.database import get_db
from app.models import ApiClient, Role, User, utcnow
from app.monitoring.ratelimit import rate_limit
from app.schemas import Token, UserCreate, UserOut
from app.security.auth import (
    Principal,
    create_access_token,
    get_current_principal,
    hash_password,
    require_roles,
    verify_password,
)
from app.services import audit

router = APIRouter(prefix="/auth", tags=["Authentication"])
login_limit = rate_limit("login", lambda: get_settings().rate_limit_login_per_minute)


@router.post("/login", response_model=Token, dependencies=[Depends(login_limit)],
             summary="OAuth 2.0 password grant - staff sign-in")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        audit.record(db, form.username, "auth.login_failed", "user", None, ip=client_ip(request))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password",
                            {"WWW-Authenticate": "Bearer"})
    user.last_login_at = utcnow()
    audit.record(db, user.email, "auth.login", "user", user.id, ip=client_ip(request))
    db.commit()
    token = create_access_token(str(user.id), [user.role.name], extra={"name": user.full_name})
    return Token(access_token=token, expires_in=get_settings().access_token_expire_minutes * 60, role=user.role.name)


@router.post("/token", response_model=Token, dependencies=[Depends(login_limit)],
             summary="OAuth 2.0 client-credentials grant - machine clients such as n8n")
def client_credentials(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form(""),
    db: Session = Depends(get_db),
):
    if grant_type != "client_credentials":
        raise HTTPException(400, {"error": "unsupported_grant_type"})
    client = db.scalar(select(ApiClient).where(ApiClient.client_id == client_id))
    if not client or not client.is_active or not verify_password(client_secret, client.client_secret_hash):
        raise HTTPException(401, {"error": "invalid_client"})
    allowed = set(client.scopes.split())
    requested = set(scope.split()) if scope else allowed
    if not requested <= allowed:
        raise HTTPException(400, {"error": "invalid_scope", "allowed": sorted(allowed)})
    token = create_access_token(client.client_id, [], token_type="client", extra={"scopes": sorted(requested)})
    return Token(access_token=token, expires_in=get_settings().access_token_expire_minutes * 60,
                 scopes=sorted(requested))


@router.get("/me", response_model=UserOut | dict)
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if principal.kind == "client":
        return {"client_id": principal.subject, "roles": principal.roles}
    return UserOut.from_user(db.get(User, principal.user_id))


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: Principal = Depends(require_roles("admin", "operations"))):
    return [UserOut.from_user(u) for u in db.scalars(select(User).order_by(User.full_name))]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), p: Principal = Depends(require_roles("admin"))):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "A user with that email already exists")
    role = db.scalar(select(Role).where(Role.name == body.role))
    user = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password),
                role_id=role.id, branch_id=body.branch_id)
    db.add(user)
    db.flush()
    audit.record(db, p.subject, "user.created", "user", user.id, {"role": body.role})
    db.commit()
    return UserOut.from_user(user)
