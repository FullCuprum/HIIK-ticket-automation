from fastapi import APIRouter

from app.schemas.common import MessageResponse
from app.schemas.ticket import TicketCreate

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=MessageResponse)
async def create_ticket(payload: TicketCreate) -> MessageResponse:
    _ = payload
    return MessageResponse(message="received")
