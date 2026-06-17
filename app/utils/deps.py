from fastapi import Header, HTTPException

from app.utils.auth import decode_access_token


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
