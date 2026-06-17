from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.utils.auth import get_user_by_username, normalize_role
from app.utils.deps import require_admin
from app.utils.password import hash_password

router = APIRouter(prefix="/users", tags=["users"])


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=normalize_role(user.role),  # type: ignore[arg-type]
        must_change_password=user.must_change_password,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[UserResponse]:
    result = await db.execute(select(User).order_by(User.username))
    return [_to_response(user) for user in result.scalars().all()]


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> UserResponse:
    existing = await get_user_by_username(db, payload.username)
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        must_change_password=True,
        is_active=True,
    )
    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already exists") from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create user") from exc

    return _to_response(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    new_username = update_data.get("username")
    if new_username and new_username != user.username:
        existing = await get_user_by_username(db, new_username)
        if existing is not None:
            raise HTTPException(status_code=400, detail="Username already exists")
        user.username = new_username

    if "role" in update_data:
        if admin.get("sub") == user.username and update_data["role"] != "admin":
            raise HTTPException(status_code=400, detail="Cannot remove admin role from yourself")
        user.role = update_data["role"]

    if "is_active" in update_data:
        if admin.get("sub") == user.username and not update_data["is_active"]:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        user.is_active = update_data["is_active"]

    if "password" in update_data:
        user.password_hash = hash_password(update_data["password"])

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already exists") from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update user") from exc

    return _to_response(user)


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if admin.get("sub") == user.username:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if user.role == "admin":
        admin_count_result = await db.execute(
            select(func.count()).select_from(User).where(User.role.in_(["admin", "manager"]), User.is_active.is_(True))
        )
        if admin_count_result.scalar_one() <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last active admin")

    response = _to_response(user)
    await db.delete(user)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete user") from exc

    return response
