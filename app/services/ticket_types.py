from __future__ import annotations

# (нормальный приоритет, высокий приоритет) — минуты
TIME_ESTIMATES: dict[str, tuple[int, int]] = {
    "repair": (60, 45),
    "software_installation": (45, 30),
    "event_support": (120, 90),
    "workspace_setup": (90, 60),
    "consultation": (30, 23),
    "video_surveillance": (90, 60),
    "other": (30, 23),
}

SKILL_BY_TYPE: dict[str, str] = {
    "repair": "hardware_support",
    "software_installation": "software_admin",
    "event_support": "event_support",
    "workspace_setup": "hardware_support",
    "consultation": "general_support",
    "video_surveillance": "hardware_support",
    "other": "general_support",
}

TICKET_TYPE_LABELS: dict[str, str] = {
    "repair": "Ремонт оборудования",
    "software_installation": "Установка ПО",
    "event_support": "Сопровождение мероприятия",
    "workspace_setup": "Подготовка рабочего места",
    "consultation": "Консультация пользователя",
    "video_surveillance": "Видеонаблюдение",
    "other": "Прочее",
}

TICKET_TYPES: tuple[str, ...] = tuple(TICKET_TYPE_LABELS.keys())

TYPE_KEYWORD_FIELDS: dict[str, str] = {
    "event_support": "event_keywords",
    "software_installation": "software_keywords",
    "repair": "repair_keywords",
    "workspace_setup": "workspace_keywords",
    "consultation": "consultation_keywords",
    "video_surveillance": "video_surveillance_keywords",
    "other": "other_keywords",
}
