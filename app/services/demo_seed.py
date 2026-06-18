"""Демонстрационные данные: пользователи, сотрудники, заявки и расписание на 2 недели."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.employee import Employee
from app.models.schedule import Schedule
from app.models.ticket import Ticket
from app.models.user import User
from app.services.event_support import EVENT_TOTAL_MINUTES, event_slot_bounds
from app.services.schedule_availability import EVENT_MANUAL_REVIEW_COMMENT
from app.services.schedule_executors import set_schedule_executors
from app.services.scheduler import ensure_default_employees
from app.utils.datetime_utils import get_app_timezone, local_today, now_local
from app.utils.password import hash_password

DEMO_PREFIX = "[демо]"
DEMO_PASSWORD = "demo123"

DEMO_USERS = [
    {
        "username": "kozlov",
        "full_name": "Козлов Алексей Николаевич",
        "role": "user",
    },
    {
        "username": "smirnova",
        "full_name": "Смирнова Елена Викторовна",
        "role": "user",
    },
    {
        "username": "orlova",
        "full_name": "Орлова Мария Петровна",
        "role": "user",
    },
    {
        "username": "morozova",
        "full_name": "Морозова Анна Сергеевна",
        "role": "employee",
    },
]

EXTRA_EMPLOYEES = [
    {
        "full_name": "Морозова Анна Сергеевна",
        "position": "Инженер аппаратного обеспечения",
        "skills": ["hardware_support", "general_support"],
        "max_parallel_tasks": 2,
        "is_active": True,
        "work_start_hour": 9,
        "work_end_hour": 18,
        "phone": "+7 (900) 444-44-44",
        "email": "morozova@hiik.sibguti.ru",
    },
    {
        "full_name": "Козлов Алексей Николаевич",
        "position": "Инженер видеонаблюдения",
        "skills": ["video_surveillance", "network_engineer"],
        "max_parallel_tasks": 1,
        "is_active": True,
        "work_start_hour": 9,
        "work_end_hour": 17,
        "phone": "+7 (900) 555-55-55",
        "email": "kozlov.a@hiik.sibguti.ru",
    },
    {
        "full_name": "Волков Дмитрий Игоревич",
        "position": "Инженер (неактивен)",
        "skills": ["general_support"],
        "max_parallel_tasks": 1,
        "is_active": False,
        "work_start_hour": 9,
        "work_end_hour": 18,
        "phone": "+7 (900) 666-66-66",
        "email": "volkov@hiik.sibguti.ru",
    },
]


@dataclass(frozen=True)
class _ScheduleSpec:
    day_offset: int
    start_hour: int
    start_minute: int
    duration_minutes: int
    executor_names: tuple[str, ...]
    slot_type: str
    approval_status: str
    manager_comment: str | None = None


@dataclass(frozen=True)
class _TicketSpec:
    suffix: str
    raw_text: str
    status: str
    creator: str
    building: str | None
    location: str | None
    problem: str | None
    ticket_type: str | None
    priority: str
    minutes: int | None
    skill: str | None
    created_days_ago: int = 0
    completed_days_ago: int | None = None
    event_datetime: datetime | None = None
    schedule: _ScheduleSpec | None = None


def _local_dt(day: date, hour: int, minute: int = 0) -> datetime:
    tz = get_app_timezone()
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


def _day(offset: int) -> date:
    return local_today() + timedelta(days=offset)


def _build_ticket_specs() -> list[_TicketSpec]:
    today = local_today()
    event_friday = _local_dt(_day(5), 14, 0)
    event_next_week = _local_dt(_day(10), 10, 30)
    event_conflict = _local_dt(_day(3), 15, 0)
    event_start, event_end = event_slot_bounds(event_friday)
    webinar_start, _webinar_end = event_slot_bounds(event_next_week)

    return [
        _TicketSpec(
            suffix="новая",
            raw_text="[демо] Только что поступила заявка, ещё не обработана.",
            status="new",
            creator="kozlov",
            building=None,
            location=None,
            problem=None,
            ticket_type=None,
            priority="low",
            minutes=None,
            skill=None,
            created_days_ago=0,
        ),
        _TicketSpec(
            suffix="уточнение",
            raw_text="[демо] Не работает интернет, срочно нужна помощь.",
            status="need_clarification",
            creator="smirnova",
            building=None,
            location=None,
            problem="Не работает интернет",
            ticket_type="repair",
            priority="high",
            minutes=60,
            skill="network_engineer",
            created_days_ago=1,
        ),
        _TicketSpec(
            suffix="очередь-планирования",
            raw_text="[демо] Установить Adobe Reader в кабинете 208 второго корпуса.",
            status="ready_for_scheduling",
            creator="orlova",
            building="corpus_2",
            location="208",
            problem="Установка Adobe Reader",
            ticket_type="software_installation",
            priority="low",
            minutes=45,
            skill="software_admin",
            created_days_ago=0,
        ),
        _TicketSpec(
            suffix="ожидает-утверждения",
            raw_text="[демо] Срочно! Не работает проектор в ауд. 301 первого корпуса.",
            status="scheduled",
            creator="kozlov",
            building="corpus_1",
            location="301",
            problem="Не работает проектор",
            ticket_type="repair",
            priority="high",
            minutes=60,
            skill="hardware_support",
            created_days_ago=1,
            schedule=_ScheduleSpec(
                day_offset=1,
                start_hour=10,
                start_minute=0,
                duration_minutes=60,
                executor_names=("Морозова Анна Сергеевна",),
                slot_type="high_priority",
                approval_status="pending",
            ),
        ),
        _TicketSpec(
            suffix="мероприятие-ожидает",
            raw_text=(
                f"[демо] Мероприятие {event_friday.strftime('%d.%m.%Y %H:%M')} "
                "в ауд. 401 первого корпуса — настройка звука и трансляции."
            ),
            status="scheduled",
            creator="smirnova",
            building="corpus_1",
            location="401",
            problem="Настройка звука на мероприятии",
            ticket_type="event_support",
            priority="high",
            minutes=EVENT_TOTAL_MINUTES,
            skill="event_support",
            created_days_ago=2,
            event_datetime=event_friday,
            schedule=_ScheduleSpec(
                day_offset=5,
                start_hour=event_start.hour,
                start_minute=event_start.minute,
                duration_minutes=EVENT_TOTAL_MINUTES,
                executor_names=(
                    "Сидоров Сидор Сидорович",
                    "Иванов Иван Иванович",
                ),
                slot_type="high_priority",
                approval_status="pending",
            ),
        ),
        _TicketSpec(
            suffix="ручная-проверка",
            raw_text=(
                f"[демо] Конференция {event_conflict.strftime('%d.%m.%Y %H:%M')} "
                "в ауд. 210 второго корпуса, возможен конфликт расписания."
            ),
            status="scheduled",
            creator="kozlov",
            building="corpus_2",
            location="210",
            problem="Техническое сопровождение конференции",
            ticket_type="event_support",
            priority="high",
            minutes=EVENT_TOTAL_MINUTES,
            skill="event_support",
            created_days_ago=1,
            event_datetime=event_conflict,
            schedule=_ScheduleSpec(
                day_offset=3,
                start_hour=14,
                start_minute=30,
                duration_minutes=EVENT_TOTAL_MINUTES,
                executor_names=("Сидоров Сидор Сидорович",),
                slot_type="high_priority",
                approval_status="pending",
                manager_comment=EVENT_MANUAL_REVIEW_COMMENT,
            ),
        ),
        _TicketSpec(
            suffix="отклонена",
            raw_text="[демо] Перенести сервер в кабинет 999 первого корпуса.",
            status="rejected",
            creator="orlova",
            building="corpus_1",
            location="999",
            problem="Перенос серверного оборудования",
            ticket_type="other",
            priority="low",
            minutes=120,
            skill="network_engineer",
            created_days_ago=3,
            schedule=_ScheduleSpec(
                day_offset=2,
                start_hour=11,
                start_minute=0,
                duration_minutes=120,
                executor_names=("Иванов Иван Иванович",),
                slot_type="normal",
                approval_status="rejected",
                manager_comment="Некорректный кабинет, уточните локацию и согласуйте с администрацией.",
            ),
        ),
        _TicketSpec(
            suffix="сегодня-утверждена",
            raw_text="[демо] Не работает Wi-Fi в ауд. 214 первого корпуса.",
            status="approved",
            creator="user",
            building="corpus_1",
            location="214",
            problem="Не работает Wi-Fi",
            ticket_type="repair",
            priority="high",
            minutes=60,
            skill="network_engineer",
            created_days_ago=2,
            schedule=_ScheduleSpec(
                day_offset=0,
                start_hour=11,
                start_minute=0,
                duration_minutes=60,
                executor_names=("Иванов Иван Иванович",),
                slot_type="high_priority",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="сегодня-параллель-1",
            raw_text="[демо] Не печатает принтер в кабинете 215 первого корпуса.",
            status="approved",
            creator="smirnova",
            building="corpus_1",
            location="215",
            problem="Не печатает принтер",
            ticket_type="repair",
            priority="low",
            minutes=45,
            skill="hardware_support",
            created_days_ago=1,
            schedule=_ScheduleSpec(
                day_offset=0,
                start_hour=11,
                start_minute=15,
                duration_minutes=45,
                executor_names=("Иванов Иван Иванович",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="сегодня-параллель-2",
            raw_text="[демо] Настроить сетевой доступ для нового ПК в каб. 216.",
            status="approved",
            creator="kozlov",
            building="corpus_1",
            location="216",
            problem="Настройка сетевого доступа",
            ticket_type="repair",
            priority="low",
            minutes=30,
            skill="network_engineer",
            created_days_ago=1,
            schedule=_ScheduleSpec(
                day_offset=0,
                start_hour=11,
                start_minute=30,
                duration_minutes=30,
                executor_names=("Иванов Иван Иванович",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="завтра-по",
            raw_text="[демо] Установить Microsoft Office в компьютерном классе 105 второго корпуса.",
            status="approved",
            creator="orlova",
            building="corpus_2",
            location="105",
            problem="Установка Microsoft Office",
            ticket_type="software_installation",
            priority="low",
            minutes=90,
            skill="software_admin",
            created_days_ago=2,
            schedule=_ScheduleSpec(
                day_offset=1,
                start_hour=13,
                start_minute=0,
                duration_minutes=90,
                executor_names=("Петров Пётр Петрович",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="массовый-ремонт",
            raw_text="[демо] Не работают 12 компьютеров в компьютерном классе 201 второго корпуса.",
            status="approved",
            creator="smirnova",
            building="corpus_2",
            location="201",
            problem="Массовый сбой ПК в классе",
            ticket_type="repair",
            priority="high",
            minutes=180,
            skill="network_engineer",
            created_days_ago=3,
            schedule=_ScheduleSpec(
                day_offset=2,
                start_hour=9,
                start_minute=30,
                duration_minutes=180,
                executor_names=(
                    "Иванов Иван Иванович",
                    "Морозова Анна Сергеевна",
                ),
                slot_type="high_priority",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="общежитие-1",
            raw_text="[демо] На вахте первого общежития не работает компьютер.",
            status="approved",
            creator="orlova",
            building="dorm_1",
            location="вахта",
            problem="Не работает компьютер на вахте",
            ticket_type="repair",
            priority="low",
            minutes=60,
            skill="hardware_support",
            created_days_ago=2,
            schedule=_ScheduleSpec(
                day_offset=1,
                start_hour=15,
                start_minute=0,
                duration_minutes=60,
                executor_names=("Морозова Анна Сергеевна",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="общежитие-2",
            raw_text="[демо] Не работает Wi-Fi в комнате 315 второго общежития.",
            status="approved",
            creator="orlova",
            building="dorm_2",
            location="315",
            problem="Не работает Wi-Fi",
            ticket_type="repair",
            priority="low",
            minutes=45,
            skill="network_engineer",
            created_days_ago=1,
            schedule=_ScheduleSpec(
                day_offset=4,
                start_hour=16,
                start_minute=0,
                duration_minutes=45,
                executor_names=("Козлов Алексей Николаевич",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="видеонаблюдение",
            raw_text="[демо] Пропал сигнал с камеры у входа в первый корпус.",
            status="approved",
            creator="kozlov",
            building="corpus_1",
            location="вход",
            problem="Нет сигнала с камеры",
            ticket_type="video_surveillance",
            priority="high",
            minutes=90,
            skill="video_surveillance",
            created_days_ago=2,
            schedule=_ScheduleSpec(
                day_offset=3,
                start_hour=10,
                start_minute=0,
                duration_minutes=90,
                executor_names=("Козлов Алексей Николаевич",),
                slot_type="high_priority",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="консультация",
            raw_text="[демо] Подскажите, как настроить VPN на домашнем ноутбуке для работы.",
            status="approved",
            creator="user",
            building="corpus_1",
            location="112",
            problem="Консультация по VPN",
            ticket_type="consultation",
            priority="low",
            minutes=30,
            skill="general_support",
            created_days_ago=4,
            schedule=_ScheduleSpec(
                day_offset=6,
                start_hour=14,
                start_minute=0,
                duration_minutes=30,
                executor_names=("Петров Пётр Петрович",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="рабочее-место",
            raw_text="[демо] Подготовить рабочее место для нового сотрудника в кабинете 112.",
            status="approved",
            creator="smirnova",
            building="corpus_1",
            location="112",
            problem="Подготовка рабочего места",
            ticket_type="workspace_setup",
            priority="low",
            minutes=60,
            skill="general_support",
            created_days_ago=3,
            schedule=_ScheduleSpec(
                day_offset=7,
                start_hour=9,
                start_minute=0,
                duration_minutes=60,
                executor_names=("Морозова Анна Сергеевна",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="мероприятие-утверждено",
            raw_text=(
                f"[демо] Вебинар {event_next_week.strftime('%d.%m.%Y %H:%M')} "
                "в ауд. 301 первого корпуса."
            ),
            status="approved",
            creator="kozlov",
            building="corpus_1",
            location="301",
            problem="Техническое сопровождение вебинара",
            ticket_type="event_support",
            priority="high",
            minutes=EVENT_TOTAL_MINUTES,
            skill="event_support",
            created_days_ago=5,
            event_datetime=event_next_week,
            schedule=_ScheduleSpec(
                day_offset=10,
                start_hour=webinar_start.hour,
                start_minute=webinar_start.minute,
                duration_minutes=EVENT_TOTAL_MINUTES,
                executor_names=(
                    "Сидоров Сидор Сидорович",
                    "Иванов Иван Иванович",
                ),
                slot_type="high_priority",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="неделя-2",
            raw_text="[демо] Заменить кабель в серверной второго корпуса.",
            status="approved",
            creator="admin",
            building="corpus_2",
            location="серверная",
            problem="Замена сетевого кабеля",
            ticket_type="repair",
            priority="low",
            minutes=120,
            skill="network_engineer",
            created_days_ago=4,
            schedule=_ScheduleSpec(
                day_offset=12,
                start_hour=10,
                start_minute=0,
                duration_minutes=120,
                executor_names=("Иванов Иван Иванович",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="резервный-слот",
            raw_text="[демо] Диагностика сетевого коммутатора на 3 этаже первого корпуса.",
            status="approved",
            creator="smirnova",
            building="corpus_1",
            location="3 этаж",
            problem="Диагностика коммутатора",
            ticket_type="repair",
            priority="low",
            minutes=60,
            skill="network_engineer",
            created_days_ago=3,
            schedule=_ScheduleSpec(
                day_offset=8,
                start_hour=17,
                start_minute=0,
                duration_minutes=60,
                executor_names=("Иванов Иван Иванович",),
                slot_type="reserve",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="выполнена-вчера",
            raw_text="[демо] Не работала розетка в ауд. 102 первого корпуса.",
            status="completed",
            creator="user",
            building="corpus_1",
            location="102",
            problem="Не работала розетка",
            ticket_type="repair",
            priority="low",
            minutes=30,
            skill="hardware_support",
            created_days_ago=5,
            completed_days_ago=1,
            schedule=_ScheduleSpec(
                day_offset=-1,
                start_hour=14,
                start_minute=0,
                duration_minutes=30,
                executor_names=("Морозова Анна Сергеевна",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
        _TicketSpec(
            suffix="выполнена-неделя",
            raw_text="[демо] Установлен принтер в кабинете 203 второго корпуса.",
            status="completed",
            creator="orlova",
            building="corpus_2",
            location="203",
            problem="Установка принтера",
            ticket_type="repair",
            priority="low",
            minutes=60,
            skill="hardware_support",
            created_days_ago=10,
            completed_days_ago=7,
            schedule=_ScheduleSpec(
                day_offset=-7,
                start_hour=11,
                start_minute=0,
                duration_minutes=60,
                executor_names=("Морозова Анна Сергеевна",),
                slot_type="normal",
                approval_status="approved",
            ),
        ),
    ]


async def _demo_data_exists(db: AsyncSession) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.raw_text.startswith(DEMO_PREFIX))
    )
    return (result.scalar_one() or 0) > 0


async def _ensure_user(
    db: AsyncSession,
    *,
    username: str,
    full_name: str,
    role: str,
) -> User:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is not None:
        if not user.full_name:
            user.full_name = full_name
        return user

    user = User(
        username=username,
        full_name=full_name,
        password_hash=hash_password(DEMO_PASSWORD),
        role=role,
        must_change_password=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _ensure_employee(db: AsyncSession, data: dict) -> Employee:
    result = await db.execute(select(Employee).where(Employee.full_name == data["full_name"]))
    employee = result.scalar_one_or_none()
    if employee is not None:
        return employee

    employee = Employee(**data)
    db.add(employee)
    await db.flush()
    return employee


async def _employee_map(db: AsyncSession) -> dict[str, Employee]:
    result = await db.execute(select(Employee))
    return {employee.full_name: employee for employee in result.scalars().all()}


async def _link_employee_user(db: AsyncSession, employee: Employee, user: User) -> None:
    if employee.user_id is None:
        employee.user_id = user.id
    user.full_name = employee.full_name
    user.role = "employee"


async def _create_ticket(
    db: AsyncSession,
    spec: _TicketSpec,
    *,
    employees: dict[str, Employee],
) -> Ticket:
    created_at = now_local() - timedelta(days=spec.created_days_ago, hours=2)
    ticket = Ticket(
        raw_text=spec.raw_text,
        status=spec.status,
        extracted_location=spec.location,
        extracted_building=spec.building,
        extracted_problem=spec.problem,
        ticket_type=spec.ticket_type,
        priority=spec.priority,
        estimated_minutes=spec.minutes,
        required_skill=spec.skill,
        event_datetime=spec.event_datetime,
        creator_username=spec.creator,
        created_at=created_at,
        updated_at=created_at,
    )
    if spec.completed_days_ago is not None:
        ticket.completed_at = now_local() - timedelta(days=spec.completed_days_ago, hours=1)

    db.add(ticket)
    await db.flush()

    if spec.schedule is not None:
        schedule_spec = spec.schedule
        day = _day(schedule_spec.day_offset)
        start_time = _local_dt(day, schedule_spec.start_hour, schedule_spec.start_minute)
        end_time = start_time + timedelta(minutes=schedule_spec.duration_minutes)
        executor_ids = [
            employees[name].id
            for name in schedule_spec.executor_names
            if name in employees
        ]
        if not executor_ids:
            raise ValueError(f"No executors resolved for demo ticket: {spec.suffix}")

        schedule = Schedule(
            ticket_id=ticket.id,
            employee_id=executor_ids[0],
            start_time=start_time,
            end_time=end_time,
            slot_type=schedule_spec.slot_type,
        )
        db.add(schedule)
        await db.flush()
        await set_schedule_executors(db, schedule, executor_ids)

        approval = Approval(
            proposed_schedule_id=schedule.id,
            status=schedule_spec.approval_status,
            manager_comment=schedule_spec.manager_comment,
        )
        db.add(approval)

    return ticket


async def ensure_demo_dataset(db: AsyncSession) -> bool:
    """
    Заполняет БД демонстрационными данными один раз.
    Возвращает True, если сид выполнен; False — если данные уже есть.
    """
    if await _demo_data_exists(db):
        return False

    await ensure_default_employees(db)

    for employee_data in EXTRA_EMPLOYEES:
        await _ensure_employee(db, employee_data)

    for demo_user in DEMO_USERS:
        user = await _ensure_user(
            db,
            username=demo_user["username"],
            full_name=demo_user["full_name"],
            role=demo_user["role"],
        )
        if demo_user["role"] == "employee":
            result = await db.execute(
                select(Employee).where(Employee.full_name == demo_user["full_name"])
            )
            employee = result.scalar_one_or_none()
            if employee is not None:
                await _link_employee_user(db, employee, user)

    employees = await _employee_map(db)

    for spec in _build_ticket_specs():
        await _create_ticket(db, spec, employees=employees)

    await db.flush()
    return True
