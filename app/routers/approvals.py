from fastapi import APIRouter

from app.schemas.common import MessageResponse

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/submit", response_model=MessageResponse)
async def submit_approval() -> MessageResponse:
    return MessageResponse(message="approval request created")
