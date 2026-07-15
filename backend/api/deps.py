"""Shared FastAPI dependencies."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.api.security import decode_access_token
from backend.db.base import get_session
from backend.db.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", ""))
    except (jwt.PyJWTError, ValueError) as exc:
        raise credentials_error from exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user
