from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()

DEMO_USERS: dict[str, dict[str, str]] = {
    "admin": {"password": "admin", "role": "manager"},
    "employee": {"password": "employee", "role": "employee"},
    "user": {"password": "user", "role": "user"},
}


def authenticate_user(username: str, password: str) -> dict[str, str] | None:
    user = DEMO_USERS.get(username)
    if user and user["password"] == password:
        return {"username": username, "role": user["role"]}
    return None


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
