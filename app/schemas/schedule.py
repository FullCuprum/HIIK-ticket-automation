from datetime import datetime

from pydantic import BaseModel


class ScheduleEmployeeOption(BaseModel):
    id: int
    full_name: str


class ScheduleItemResponse(BaseModel):
    id: int
    ticket_id: int
    employee_id: int
    employee_name: str
    start_time: datetime
    end_time: datetime
    slot_type: str
    description: str | None = None
    location: str | None = None


class ApprovalItemResponse(BaseModel):
    id: int
    ticket_id: int
    proposed_schedule_id: int
    status: str
    description: str | None = None
    location: str | None = None
    employee_name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime


class ApprovalActionRequest(BaseModel):
    manager_comment: str | None = None
