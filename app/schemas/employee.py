from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmployeeBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    position: str = Field(..., min_length=1, max_length=100)
    skills: list[str] = Field(default_factory=list)
    max_parallel_tasks: int = Field(default=1, ge=1, le=10)
    is_active: bool = True
    work_start_hour: int = Field(default=9, ge=0, le=23)
    work_end_hour: int = Field(default=18, ge=1, le=24)
    phone: str | None = None
    email: str | None = None

    @field_validator("work_end_hour")
    @classmethod
    def validate_work_hours(cls, end_hour: int, info) -> int:
        start_hour = info.data.get("work_start_hour", 9)
        if end_hour <= start_hour:
            raise ValueError("work_end_hour must be greater than work_start_hour")
        return end_hour


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    position: str | None = Field(default=None, min_length=1, max_length=100)
    skills: list[str] | None = None
    max_parallel_tasks: int | None = Field(default=None, ge=1, le=10)
    is_active: bool | None = None
    work_start_hour: int | None = Field(default=None, ge=0, le=23)
    work_end_hour: int | None = Field(default=None, ge=1, le=24)
    phone: str | None = None
    email: str | None = None


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_minutes_per_day: int
    scheduled_minutes_today: int
    workload_percent: float
    tasks_today: int


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    average_workload_percent: float
