from fastapi import Header, HTTPException

from app.utils.auth import decode_access_token


async def get_optional_username(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        return None

    return payload.get("sub")


async def require_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return payload


async def require_admin(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    role = payload.get("role")
    if role not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Admin access required")

    return payload
