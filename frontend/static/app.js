const API_BASE_URL = window.APP_CONFIG?.apiBaseUrl || "http://localhost:8000";
const APP_TIMEZONE = window.APP_CONFIG?.timezone || "Asia/Vladivostok";

const FIELD_LABELS = {
  location: "Кабинет / аудитория",
  problem_description: "Описание проблемы",
  ticket_type: "Тип заявки",
  priority: "Срочность",
  estimated_minutes: "Время выполнения (мин)",
  required_skill: "Требуемый навык",
};

const TICKET_TYPE_LABELS = {
  repair: "Ремонт",
  software_installation: "Установка ПО",
  event_support: "Сопровождение мероприятия",
  other: "Другое",
};

const PRIORITY_LABELS = {
  low: "Обычная",
  high: "Высокая",
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

function normalizeRole(role, username = "") {
  if (role === "manager" || role === "admin") {
    return "manager";
  }
  if (!role && username === "admin") {
    return "manager";
  }
  return role;
}

function getRole() {
  let role = localStorage.getItem("user_role");
  if (!role) {
    const token = getToken();
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        role = payload.role;
      } catch {
        role = null;
      }
    }
  }
  return normalizeRole(role, getUsername());
}

function getUsername() {
  return localStorage.getItem("username");
}

function isAuthenticated() {
  return Boolean(getToken());
}

function saveAuth(data) {
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("user_role", normalizeRole(data.role, data.username));
  localStorage.setItem("username", data.username);
  initNav();
}

function clearAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user_role");
  localStorage.removeItem("username");
}

function logout() {
  clearAuth();
  window.location.href = "login.html";
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

function showToast(message, type = "info") {
  const colors = {
    info: "bg-slate-800",
    success: "bg-emerald-600",
    error: "bg-red-600",
  };

  const toast = document.createElement("div");
  toast.className = `fixed right-4 top-4 z-50 rounded-lg px-4 py-3 text-sm text-white shadow-lg ${colors[type] || colors.info}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
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
    { href: "index.html", label: "Подать заявку", roles: ["user", "employee", "manager"], key: "index" },
    { href: "schedule.html", label: "Расписание", roles: ["employee", "manager"], key: "schedule" },
    { href: "approvals.html", label: "Утверждение", roles: ["manager"], key: "approvals" },
    { href: "employees.html", label: "Сотрудники", roles: ["manager"], key: "employees" },
  ];

  const visibleLinks = links.filter((link) => !role || link.roles.includes(role));

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
  return allowedRoles.includes(normalizedRole);
}

function guardPage(allowedRoles = []) {
  if (!isAuthenticated()) {
    window.location.href = "login.html";
    return false;
  }
  const role = getRole();
  if (allowedRoles.length && !roleHasAccess(role, allowedRoles)) {
    showToast("Недостаточно прав для просмотра страницы", "error");
    window.location.href = "index.html";
    return false;
  }
  return true;
}

function initNav() {
  const navRoot = document.getElementById("app-nav");
  if (navRoot) {
    navRoot.innerHTML = renderNav(navRoot.dataset.active || "");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initNav);
} else {
  initNav();
}

window.addEventListener("pageshow", initNav);
