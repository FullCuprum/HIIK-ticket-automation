from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse
from app.services.user_seed import ensure_demo_users
from app.utils.auth import authenticate_user, create_access_token, decode_access_token, get_user_by_username, normalize_role
from app.utils.password import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return user


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    try:
        await ensure_demo_users(db)
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to initialize users") from exc

    user = await authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    role = normalize_role(user.role)
    token = create_access_token({"sub": user.username, "role": role})
    return LoginResponse(
        access_token=token,
        username=user.username,
        role=role,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password", response_model=LoginResponse)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_get_current_user),
) -> LoginResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False

    try:
        await db.commit()
        await db.refresh(current_user)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to change password") from exc

    role = normalize_role(current_user.role)
    token = create_access_token({"sub": current_user.username, "role": role})
    return LoginResponse(
        access_token=token,
        username=current_user.username,
        role=role,
        must_change_password=False,
    )
