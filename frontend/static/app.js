const API_BASE_URL = window.APP_CONFIG?.apiBaseUrl || "http://localhost:8000";
const APP_TIMEZONE = window.APP_CONFIG?.timezone || "Asia/Vladivostok";

const FIELD_LABELS = {
  building: "Здание",
  location: "Кабинет / аудитория",
  problem_description: "Описание проблемы",
  ticket_type: "Тип заявки",
  priority: "Срочность",
  estimated_minutes: "Время выполнения (мин)",
  required_skill: "Требуемый навык",
  event_datetime: "Дата и время мероприятия",
};

const TICKET_TYPE_LABELS = {
  repair: "Ремонт оборудования",
  software_installation: "Установка ПО",
  event_support: "Сопровождение мероприятия",
  workspace_setup: "Подготовка рабочего места",
  consultation: "Консультация пользователя",
  video_surveillance: "Видеонаблюдение",
  other: "Прочее",
};

const PRIORITY_LABELS = {
  low: "Обычная",
  high: "Высокая",
};

const BUILDING_LABELS = {
  corpus_1: "Первый корпус (ВО, институт, Ленина 73)",
  corpus_2: "Второй корпус (техникум, Ленина 58)",
  dorm_1: "Общежитие 1 (Ленина 56)",
  dorm_2: "Общежитие 2 (Ленина 60)",
};

function buildingLabel(value) {
  return BUILDING_LABELS[value] || value || "—";
}

function managerCommentLabel(approvalStatus) {
  if (approvalStatus === "rejected") return "Комментарий при отклонении";
  if (approvalStatus === "approved") return "Комментарий при утверждении";
  return "Комментарий к решению";
}

const TICKET_STATUS_LABELS = {
  new: "Новая",
  need_clarification: "Требует уточнения",
  ready_for_scheduling: "Готова к планированию",
  scheduled: "Запланирована",
  approved: "Утверждена",
  completed: "Выполнена",
  rejected: "Отклонена",
};

const SKILL_LABELS = {
  network_engineer: "Сетевой инженер",
  hardware_support: "Аппаратная поддержка",
  software_admin: "Администратор ПО",
  event_support: "Сопровождение мероприятий",
  general_support: "Общая поддержка",
};

function getToken() {
  return localStorage.getItem("access_token");
}

const USER_ROLE_LABELS = {
  user: "Пользователь",
  employee: "Сотрудник",
  admin: "Администратор",
};

function normalizeRole(role, username = "") {
  if (role === "manager" || role === "admin") {
    return "admin";
  }
  if (!role && username === "admin") {
    return "admin";
  }
  return role;
}

function getRole() {
  let role = null;
  const token = getToken();
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      role = payload.role;
    } catch {
      role = null;
    }
  }
  if (!role) {
    role = localStorage.getItem("user_role");
  }
  const normalized = normalizeRole(role, getUsername());
  if (normalized && normalized !== localStorage.getItem("user_role")) {
    localStorage.setItem("user_role", normalized);
  }
  return normalized;
}

function getUsername() {
  return localStorage.getItem("username");
}

function isAuthenticated() {
  return Boolean(getToken());
}

function mustChangePassword() {
  return localStorage.getItem("must_change_password") === "1";
}

function saveAuth(data) {
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("user_role", normalizeRole(data.role, data.username));
  localStorage.setItem("username", data.username);
  localStorage.setItem("must_change_password", data.must_change_password ? "1" : "0");
  initNav();
}

function clearAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user_role");
  localStorage.removeItem("username");
  localStorage.removeItem("must_change_password");
}

function redirectAfterLogin(data) {
  if (data.must_change_password) {
    window.location.href = "change-password.html";
    return;
  }

  const role = normalizeRole(data.role, data.username);
  if (role === "admin") {
    window.location.href = "employees.html";
  } else if (role === "employee") {
    window.location.href = "schedule.html";
  } else {
    window.location.href = "index.html";
  }
}

function logout() {
  clearAuth();
  window.location.href = "login.html";
}

function localTodayISO() {
  return new Date().toLocaleDateString("en-CA", { timeZone: APP_TIMEZONE });
}

function localDaysAgoISO(days) {
  const today = localTodayISO();
  const [year, month, day] = today.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function formatDisplayDate(isoDate) {
  if (!isoDate) return "—";
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
  return date.toLocaleDateString("ru-RU", {
    timeZone: APP_TIMEZONE,
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatDateTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", {
    timeZone: APP_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatAuthor(username) {
  return username || "—";
}

function toDatetimeLocalValue(value) {
  if (!value) return "";
  const date = new Date(value);
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromDatetimeLocalValue(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

function showToast(message, type = "info", duration = 3500) {
  const colors = {
    info: "bg-slate-800",
    success: "bg-emerald-600",
    error: "bg-red-600",
  };

  const toast = document.createElement("div");
  toast.className = `fixed right-4 top-4 z-50 rounded-lg px-4 py-3 text-sm text-white shadow-lg ${colors[type] || colors.info}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

function flashMessage(message, type = "error") {
  sessionStorage.setItem("flash_message", JSON.stringify({ message, type }));
}

function flushFlashMessage() {
  const raw = sessionStorage.getItem("flash_message");
  if (!raw) return;
  sessionStorage.removeItem("flash_message");
  try {
    const { message, type } = JSON.parse(raw);
    if (message) {
      showToast(message, type || "error", 7000);
    }
  } catch {
    // ignore invalid flash payload
  }
}

function redirectWithAccessDenied(target = "index.html") {
  flashMessage("Недостаточно прав для просмотра страницы", "error");
  window.location.href = target;
}

async function apiRequest(endpoint, method = "GET", body = null) {
  const headers = {
    "Content-Type": "application/json",
  };

  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const options = { method, headers };
  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
  let data = null;

  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail = data?.detail || `Ошибка запроса (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return data;
}

function renderNav(activePage = "") {
  const role = getRole();
  const username = getUsername();
  const links = [
    { href: "index.html", label: "Подать заявку", roles: ["user", "employee", "admin", "manager"], key: "index" },
    { href: "journal.html", label: "Журнал заявок", roles: ["user", "employee", "admin", "manager"], key: "journal" },
    { href: "schedule.html", label: "Расписание", roles: ["employee", "admin", "manager"], key: "schedule" },
    { href: "approvals.html", label: "Утверждение", roles: ["admin", "manager"], key: "approvals" },
    { href: "employees.html", label: "Сотрудники", roles: ["admin", "manager"], key: "employees" },
    { href: "users.html", label: "Пользователи", roles: ["admin", "manager"], key: "users" },
  ];

  const visibleLinks = links.filter((link) => role && roleHasAccess(role, link.roles));

  return `
    <header class="border-b border-slate-200 bg-white shadow-sm">
      <div class="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p class="text-xs uppercase tracking-wide text-slate-500">ХИИК СибГУТИ</p>
          <h1 class="text-lg font-semibold text-slate-800">Автоматизация заявок</h1>
        </div>
        <nav class="flex flex-wrap items-center gap-2">
          ${visibleLinks
            .map(
              (link) => `
            <a href="${link.href}"
               class="rounded-lg px-3 py-2 text-sm font-medium ${
                 activePage === link.key
                   ? "bg-blue-600 text-white"
                   : "text-slate-600 hover:bg-slate-100"
               }">
              ${link.label}
            </a>`
            )
            .join("")}
          ${
            isAuthenticated()
              ? `<button onclick="logout()" class="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">Выйти (${username || "user"})</button>`
              : `<a href="login.html" class="rounded-lg px-3 py-2 text-sm text-blue-600 hover:bg-blue-50">Войти</a>`
          }
        </nav>
      </div>
    </header>
  `;
}

function roleHasAccess(role, allowedRoles) {
  const normalizedRole = normalizeRole(role, getUsername());
  return allowedRoles.some((allowedRole) => normalizeRole(allowedRole) === normalizedRole);
}

function guardPage(allowedRoles = [], options = {}) {
  if (!isAuthenticated()) {
    window.location.href = "login.html";
    return false;
  }

  if (!options.skipPasswordChange && mustChangePassword()) {
    const currentPage = window.location.pathname.split("/").pop();
    if (currentPage !== "change-password.html") {
      window.location.href = "change-password.html";
      return false;
    }
  }

  const role = getRole();
  if (allowedRoles.length && (!role || !roleHasAccess(role, allowedRoles))) {
    redirectWithAccessDenied("index.html");
    return false;
  }
  return true;
}

function initNav() {
  const navRoot = document.getElementById("app-nav");
  if (navRoot) {
    navRoot.innerHTML = renderNav(navRoot.dataset.active || "");
  }
  flushFlashMessage();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initNav);
} else {
  initNav();
}

window.addEventListener("pageshow", initNav);
