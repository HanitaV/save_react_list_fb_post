from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer()


def issue_token(role: str = "ADMIN") -> str:
    return jwt.encode(
        {
            "sub": "local-admin",
            "role": role,
            "exp": datetime.now(timezone.utc) + timedelta(hours=8),
        },
        settings.app_secret,
        algorithm="HS256",
    )


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        return jwt.decode(
            credentials.credentials, settings.app_secret, algorithms=["HS256"]
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def require_role(*roles: str):
    def guard(user: dict = Depends(current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return guard
