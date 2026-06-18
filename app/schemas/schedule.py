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
    employee_ids: list[int] = []
    employee_names: list[str] = []
    start_time: datetime
    end_time: datetime
    slot_type: str
    description: str | None = None
    location: str | None = None
    building: str | None = None
    approval_status: str | None = None
    manager_comment: str | None = None
    ticket_status: str | None = None
    completed_at: datetime | None = None
    can_complete: bool = False
    raw_text: str
    creator_username: str | None = None


class ApprovalItemResponse(BaseModel):
    id: int
    ticket_id: int
    proposed_schedule_id: int
    employee_id: int
    status: str
    description: str | None = None
    location: str | None = None
    building: str | None = None
    employee_name: str | None = None
    employee_ids: list[int] = []
    employee_names: list[str] = []
    start_time: datetime | None = None
    end_time: datetime | None = None
    raw_text: str
    creator_username: str | None = None
    created_at: datetime


class ApprovalProposalUpdate(BaseModel):
    description: str | None = None
    location: str | None = None
    building: str | None = None
    employee_id: int | None = None
    employee_ids: list[int] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class ApprovalActionRequest(BaseModel):
    manager_comment: str | None = None
