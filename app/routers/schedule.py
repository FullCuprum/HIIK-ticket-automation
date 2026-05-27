from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/rebuild", response_model=MessageResponse)
async def rebuild_schedule() -> MessageResponse:
    return MessageResponse(message="schedule rebuild requested")
