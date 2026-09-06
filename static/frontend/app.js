"use strict";

/* Состояние клиента. Токены хранятся в localStorage ради простоты демо;
   в проде их место в HttpOnly-cookie (см. README, «Принятые допущения»). */
const state = {
  access: localStorage.getItem("clinic_access"),
  refresh: localStorage.getItem("clinic_refresh"),
  user: JSON.parse(localStorage.getItem("clinic_user") || "null"),
  doctors: [],
  selectedDoctor: null,
  authMode: "login",
  schedulePage: 1,
  adminPage: 1,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

/* Экранирование всех значений, приходящих с сервера, перед вставкой в HTML.
   Без него specialization/branch/имя врача из API дали бы stored XSS. */
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));

// Стартовая вкладка и заголовок раздела для каждой роли.
const ROLE_HOME = { patient: "doctors", doctor: "schedule", admin: "admin" };
const VIEW_TITLE = {
  doctors: "Найдите своего врача",
  appointments: "Ваши записи",
  schedule: "Моё расписание",
  newslots: "Новые слоты",
  admin: "Все записи клиники",
};
const ROLE_LABEL = { patient: "Пациент", doctor: "Врач", admin: "Администратор" };
const STATUS_LABEL = { booked: "подтверждена", cancelled: "отменена", completed: "завершена" };

function persistSession() {
  if (state.access) localStorage.setItem("clinic_access", state.access);
  else localStorage.removeItem("clinic_access");
  if (state.refresh) localStorage.setItem("clinic_refresh", state.refresh);
  else localStorage.removeItem("clinic_refresh");
  if (state.user) localStorage.setItem("clinic_user", JSON.stringify(state.user));
  else localStorage.removeItem("clinic_user");
}

function clearSession() {
  state.access = null;
  state.refresh = null;
  state.user = null;
  persistSession();
  setUser(null);
  $("#nav-count").textContent = "0";
  $("#appointments-list").innerHTML = "";
  $("#account-menu").classList.add("hidden");
  applyRole(null);
  setView("doctors"); // setView сам перезагрузит каталог для гостя
}

const api = async (path, options = {}) => {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.access) headers.Authorization = `Bearer ${state.access}`;
  const response = await fetch(`/api/${path}`, { ...options, headers });

  if (response.status === 401 && state.refresh) {
    const refreshResponse = await fetch("/api/auth/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: state.refresh }),
    });
    if (refreshResponse.ok) {
      const data = await refreshResponse.json();
      state.access = data.access;
      // Ротация: сервер возвращает новый refresh, его тоже надо сохранить.
      if (data.refresh) state.refresh = data.refresh;
      persistSession();
      return api(path, options);
    }
    // refresh мёртв — сессии больше нет, приводим UI в согласованное состояние.
    clearSession();
    throw new Error("Сессия истекла, войдите заново.");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      Object.values(data).flat?.().join(" ") || data.detail || "Не удалось выполнить запрос"
    );
  }
  return data;
};

const initials = (name) =>
  String(name || "?")
    .split(/\s+/)
    .map((word) => word[0] || "")
    .slice(0, 2)
    .join("")
    .toUpperCase() || "?";
const formatDate = (value) =>
  new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(new Date(value));
const formatTime = (value) =>
  new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
const formatDateTime = (value) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
const todayLocalISO = () => {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
};

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 3500);
}

function setUser(user) {
  state.user = user;
  persistSession();
  $("#user-status").classList.toggle("hidden", !user);
  $("#account-label").textContent = user ? user.username : "Войти";
  $("#menu-user").textContent = user ? user.username : "Гость";
  $("#menu-role").textContent = user ? ROLE_LABEL[user.role] || user.role : "";
  $(".avatar").textContent = user ? initials(user.username) : "?";
  $("#logout-button").hidden = !user;
}

// Показывает только те вкладки, что доступны роли. Гость видит пациентские.
function applyRole(role) {
  const effective = role || "patient";
  $$(".nav-link").forEach((link) => {
    const forRole =
      (link.classList.contains("role-patient") && effective === "patient") ||
      (link.classList.contains("role-doctor") && effective === "doctor") ||
      (link.classList.contains("role-admin") && effective === "admin");
    link.classList.toggle("hidden", !forRole);
  });
}

async function withBusy(button, fn) {
  if (button) button.disabled = true;
  try {
    return await fn();
  } finally {
    if (button) button.disabled = false;
  }
}

function renderPager(container, data, onNavigate) {
  const prev = data.previous ? "" : "disabled";
  const next = data.next ? "" : "disabled";
  container.innerHTML =
    `<button data-dir="prev" ${prev}>← Назад</button>` +
    `<button data-dir="next" ${next}>Вперёд →</button>`;
  container.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => onNavigate(btn.dataset.dir === "next" ? 1 : -1))
  );
}

/* ---------- Пациент: каталог врачей и запись ---------- */

async function loadDoctors() {
  const query = new URLSearchParams();
  const search = $("#search-input").value.trim();
  const branch = $("#branch-filter").value;
  if (search) query.set("search", search);
  if (branch) query.set("branch", branch);
  try {
    const data = await api(`doctors/?${query}`);
    state.doctors = data.results || data;
    const branches = [...new Set(state.doctors.map((doctor) => doctor.branch).filter(Boolean))];
    const current = branch;
    $("#branch-filter").innerHTML =
      '<option value="">Все филиалы</option>' +
      branches.map((item) => `<option value="${esc(item)}">${esc(item)}</option>`).join("");
    $("#branch-filter").value = current;
    renderDoctors();
  } catch (error) {
    const message = !state.user
      ? "Войдите в личный кабинет, чтобы увидеть каталог врачей и доступное время."
      : error.message;
    $("#doctors-list").innerHTML = `<div class="empty-state">${esc(message)}${
      !state.user ? '<br><button class="switch-auth" id="catalog-login">Войти →</button>' : ""
    }</div>`;
    $("#catalog-login")?.addEventListener("click", openAuth);
  }
}

function renderDoctors() {
  if (!state.doctors.length) {
    $("#doctors-list").innerHTML =
      '<div class="empty-state">По вашему запросу врачей не найдено.</div>';
    return;
  }
  $("#doctors-list").innerHTML = state.doctors
    .map(
      (doctor) => `<article class="doctor-card"><div class="doctor-top"><div class="doctor-avatar">${esc(
        initials(doctor.full_name)
      )}</div><div><div class="doctor-name">${esc(doctor.full_name)}</div><div class="doctor-spec">${esc(
        doctor.specialization
      )}</div></div></div><div class="doctor-branch">⌖ ${esc(
        doctor.branch || "Основной филиал"
      )}</div><button class="doctor-action" data-doctor="${esc(
        doctor.id
      )}">Выбрать время <span>→</span></button></article>`
    )
    .join("");
  $$("[data-doctor]").forEach((button) =>
    button.addEventListener("click", () => openSlots(Number(button.dataset.doctor)))
  );
}

async function openSlots(id) {
  if (!state.user) {
    openAuth();
    return;
  }
  state.selectedDoctor = state.doctors.find((doctor) => doctor.id === id);
  $("#slot-doctor-name").textContent = state.selectedDoctor.full_name;
  $("#slot-date").value = todayLocalISO();
  $("#slot-modal").classList.remove("hidden");
  await loadSlots();
}

async function loadSlots() {
  const list = $("#slots-list");
  list.innerHTML = '<div class="loading-state">Ищем свободное время...</div>';
  try {
    const slots = await api(
      `doctors/${state.selectedDoctor.id}/slots/?date=${$("#slot-date").value}`
    );
    if (!slots.length) {
      list.innerHTML = '<div class="empty-state">На эту дату свободных слотов нет.</div>';
      return;
    }
    list.innerHTML = slots
      .map(
        (slot) =>
          `<button class="slot-button" data-slot="${esc(slot.id)}">${esc(
            formatTime(slot.start_time)
          )} — ${esc(formatTime(slot.end_time))}</button>`
      )
      .join("");
    $$("[data-slot]").forEach((button) =>
      button.addEventListener("click", () => bookSlot(Number(button.dataset.slot), button))
    );
  } catch (error) {
    list.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
  }
}

async function bookSlot(id, button) {
  try {
    await withBusy(button, () =>
      api("appointments/", { method: "POST", body: JSON.stringify({ slot: id }) })
    );
    $("#slot-modal").classList.add("hidden");
    toast("Запись подтверждена. До встречи!");
    loadAppointments();
    setView("appointments");
  } catch (error) {
    toast(error.message);
  }
}

async function loadAppointments() {
  if (!state.user || state.user.role !== "patient") return;
  try {
    const data = await api("appointments/");
    const appointments = data.results || data;
    $("#nav-count").textContent = appointments.filter((item) => item.status === "booked").length;
    $("#appointments-list").innerHTML = appointments.length
      ? appointments
          .map(
            (item) =>
              `<article class="appointment-card"><div class="appointment-date"><strong>${new Date(
                item.start_time
              ).getDate()}</strong>${new Intl.DateTimeFormat("ru-RU", { month: "short" }).format(
                new Date(item.start_time)
              )}</div><div class="appointment-info"><strong>${esc(
                item.doctor_name
              )}</strong><small>${esc(item.specialization)} · ${esc(
                item.branch || "Филиал"
              )}<br>${esc(formatTime(item.start_time))} — ${esc(
                formatTime(item.end_time)
              )}</small></div><div><span class="status ${
                item.status === "booked" ? "" : "cancelled"
              }">${esc(STATUS_LABEL[item.status] || item.status)}</span>${
                item.status === "booked"
                  ? `<button class="cancel-button" data-cancel="${esc(item.id)}">Отменить</button>`
                  : ""
              }</div></article>`
          )
          .join("")
      : '<div class="empty-state">У вас пока нет записей.<br><button class="switch-auth" data-view="doctors">Найти врача →</button></div>';
    $$("[data-cancel]").forEach((button) =>
      button.addEventListener("click", () => cancelAppointment(Number(button.dataset.cancel), button))
    );
    $$('[data-view="doctors"]').forEach((button) =>
      button.addEventListener("click", () => setView("doctors"))
    );
  } catch (error) {
    $("#appointments-list").innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
  }
}

async function cancelAppointment(id, button) {
  if (!confirm("Отменить эту запись?")) return;
  try {
    await withBusy(button, () => api(`appointments/${id}/cancel/`, { method: "POST" }));
    toast("Запись отменена");
    loadAppointments();
  } catch (error) {
    toast(error.message);
  }
}

/* ---------- Врач: расписание и создание слотов ---------- */

async function loadSchedule() {
  const list = $("#schedule-list");
  list.innerHTML = '<div class="loading-state">Загружаем расписание...</div>';
  try {
    const data = await api(`slots/mine/?page=${state.schedulePage}`);
    const slots = data.results || [];
    list.innerHTML = slots.length
      ? slots
          .map((slot) => {
            const busy = slot.booked_by;
            return `<article class="appointment-card"><div class="appointment-date"><strong>${new Date(
              slot.start_time
            ).getDate()}</strong>${new Intl.DateTimeFormat("ru-RU", { month: "short" }).format(
              new Date(slot.start_time)
            )}</div><div class="appointment-info"><strong>${esc(
              formatTime(slot.start_time)
            )} — ${esc(formatTime(slot.end_time))}</strong><small>${
              busy
                ? "Пациент: " + esc(busy.patient_username)
                : "свободно"
            }</small></div><div><span class="status ${busy ? "" : "cancelled"}">${
              busy ? esc(STATUS_LABEL[busy.status] || busy.status) : "открыт"
            }</span></div></article>`;
          })
          .join("")
      : '<div class="empty-state">В расписании пока нет слотов. Создайте их во вкладке «Добавить слоты».</div>';
    renderPager($("#schedule-pager"), data, (delta) => {
      state.schedulePage = Math.max(1, state.schedulePage + delta);
      loadSchedule();
    });
  } catch (error) {
    list.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
    $("#schedule-pager").innerHTML = "";
  }
}

// date + time из локальных полей формы → ISO 8601 в UTC (с суффиксом Z).
function localToIso(dateStr, timeStr) {
  return new Date(`${dateStr}T${timeStr}:00`).toISOString();
}

$("#newslots-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = Object.fromEntries(new FormData(event.target).entries());
  $("#newslots-error").textContent = "";
  $("#newslots-result").innerHTML = "";
  let payload;
  try {
    payload = {
      start_time: localToIso(form.date, form.start),
      end_time: localToIso(form.date, form.end),
      slot_duration_minutes: Number(form.duration),
    };
  } catch {
    $("#newslots-error").textContent = "Проверьте дату и время.";
    return;
  }
  try {
    const created = await withBusy($("#newslots-submit"), () =>
      api("slots/", { method: "POST", body: JSON.stringify(payload) })
    );
    toast(`Создано слотов: ${created.length}`);
    $("#newslots-result").innerHTML = created
      .map(
        (slot) =>
          `<span class="slot-button">${esc(formatTime(slot.start_time))} — ${esc(
            formatTime(slot.end_time)
          )}</span>`
      )
      .join("");
    state.schedulePage = 1;
  } catch (error) {
    $("#newslots-error").textContent = error.message;
  }
});

/* ---------- Админ: все записи с фильтрами ---------- */

async function primeAdminFilters() {
  if ($("#admin-doctor").options.length > 1) return;
  try {
    const data = await api("doctors/?page_size=100");
    const doctors = data.results || data;
    $("#admin-doctor").innerHTML =
      '<option value="">Все врачи</option>' +
      doctors
        .map((d) => `<option value="${esc(d.id)}">${esc(d.full_name)}</option>`)
        .join("");
    const branches = [...new Set(doctors.map((d) => d.branch).filter(Boolean))];
    $("#admin-branch").innerHTML =
      '<option value="">Все филиалы</option>' +
      branches.map((b) => `<option value="${esc(b)}">${esc(b)}</option>`).join("");
  } catch {
    /* фильтры останутся с одним пунктом — не критично */
  }
}

async function loadAdmin() {
  await primeAdminFilters();
  const list = $("#admin-list");
  list.innerHTML = '<div class="loading-state">Загружаем записи...</div>';
  const query = new URLSearchParams({ page: state.adminPage });
  const map = {
    doctor: "#admin-doctor",
    branch: "#admin-branch",
    status: "#admin-status",
    date_from: "#admin-from",
    date_to: "#admin-to",
  };
  for (const [param, selector] of Object.entries(map)) {
    const value = $(selector).value;
    if (value) query.set(param, value);
  }
  try {
    const data = await api(`admin/appointments/?${query}`);
    const rows = data.results || [];
    list.innerHTML = rows.length
      ? `<table class="admin-table"><thead><tr><th>Пациент</th><th>Врач</th><th>Специализация</th><th>Филиал</th><th>Приём</th><th>Статус</th></tr></thead><tbody>${rows
          .map(
            (r) =>
              `<tr><td>${esc(r.patient_username)}</td><td>${esc(
                r.doctor_username
              )}</td><td>${esc(r.specialization)}</td><td>${esc(
                r.branch || "—"
              )}</td><td>${esc(formatDateTime(r.start_time))} – ${esc(
                formatTime(r.end_time)
              )}</td><td><span class="status ${
                r.status === "booked" ? "" : "cancelled"
              }">${esc(r.status)}</span></td></tr>`
          )
          .join("")}</tbody></table>`
      : '<div class="empty-state">Записей по этим фильтрам нет.</div>';
    renderPager($("#admin-pager"), data, (delta) => {
      state.adminPage = Math.max(1, state.adminPage + delta);
      loadAdmin();
    });
  } catch (error) {
    list.innerHTML = `<div class="empty-state">${esc(error.message)}</div>`;
    $("#admin-pager").innerHTML = "";
  }
}

["#admin-doctor", "#admin-branch", "#admin-status", "#admin-from", "#admin-to"].forEach((sel) =>
  $(sel).addEventListener("change", () => {
    state.adminPage = 1;
    loadAdmin();
  })
);
$("#admin-clear").addEventListener("click", () => {
  ["#admin-doctor", "#admin-branch", "#admin-status", "#admin-from", "#admin-to"].forEach(
    (sel) => ($(sel).value = "")
  );
  state.adminPage = 1;
  loadAdmin();
});

/* ---------- Навигация между вкладками ---------- */

function setView(view) {
  $$(".nav-link").forEach((item) =>
    item.classList.toggle("active", item.dataset.view === view)
  );
  const panels = {
    doctors: "#doctors-view",
    appointments: "#appointments-view",
    schedule: "#schedule-view",
    newslots: "#newslots-view",
    admin: "#admin-view",
  };
  for (const [name, selector] of Object.entries(panels)) {
    $(selector).classList.toggle("hidden", name !== view);
  }
  $("#view-title").textContent = VIEW_TITLE[view] || "Личный кабинет";
  if (view === "doctors" && (!state.user || state.user.role === "patient")) loadDoctors();
  if (view === "appointments") loadAppointments();
  if (view === "schedule") loadSchedule();
  if (view === "admin") loadAdmin();
  if (view === "newslots" && !$('#newslots-form [name="date"]').value) {
    $('#newslots-form [name="date"]').value = todayLocalISO();
  }
}

function goHome() {
  const role = state.user?.role;
  applyRole(role);
  setView(ROLE_HOME[role] || "doctors");
}

/* ---------- Аутентификация ---------- */

function openAuth() {
  state.authMode = "login";
  $("#auth-modal").classList.remove("hidden");
  updateAuthModal();
}

function updateAuthModal() {
  const register = state.authMode === "register";
  $("#auth-title").textContent = register ? "Создайте аккаунт" : "С возвращением";
  $("#auth-subtitle").textContent = register
    ? "Записывайтесь к врачу в пару кликов."
    : "Войдите, чтобы управлять своими записями.";
  $("#auth-submit").textContent = register ? "Зарегистрироваться" : "Войти";
  $("#switch-auth").textContent = register
    ? "Уже есть аккаунт? Войти"
    : "Нет аккаунта? Зарегистрироваться";
  $$(".register-only").forEach((item) => item.classList.toggle("hidden", !register));
  $("#auth-error").textContent = "";
}

async function doLogin(username, password) {
  const data = await api("auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  state.access = data.access;
  state.refresh = data.refresh;
  persistSession();
  setUser(data.user);
  $("#auth-modal").classList.add("hidden");
  toast(`Рады видеть, ${data.user.username}!`);
  state.schedulePage = 1;
  state.adminPage = 1;
  goHome();
  if (data.user.role === "patient") loadAppointments();
}

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = Object.fromEntries(form.entries());
  const register = state.authMode === "register";
  try {
    if (register) {
      await api("auth/register/", { method: "POST", body: JSON.stringify(payload) });
      // Сразу логиним — отдельный шаг «теперь войдите» не нужен.
      await doLogin(payload.username, payload.password);
      return;
    }
    await doLogin(payload.username, payload.password);
  } catch (error) {
    $("#auth-error").textContent = error.message;
  }
});

$("#switch-auth").addEventListener("click", () => {
  state.authMode = state.authMode === "login" ? "register" : "login";
  updateAuthModal();
});

$("#account-button").addEventListener("click", () => {
  if (!state.user) {
    openAuth();
    return;
  }
  $("#account-menu").classList.toggle("hidden");
});

document.addEventListener("click", (event) => {
  if (!$("#account-menu").classList.contains("hidden") && !$(".account-area").contains(event.target)) {
    $("#account-menu").classList.add("hidden");
  }
});

$("#logout-button").addEventListener("click", async () => {
  if (!state.user) return;
  // Просим сервер отозвать refresh; на любой исход всё равно чистим клиент.
  try {
    if (state.refresh) {
      await api("auth/logout/", { method: "POST", body: JSON.stringify({ refresh: state.refresh }) });
    }
  } catch (error) {
    /* refresh мог уже протухнуть — не мешаем локальному выходу */
  }
  clearSession();
  toast("Вы вышли из аккаунта");
});

$$("[data-close]").forEach((button) =>
  button.addEventListener("click", () => $("#" + button.dataset.close).classList.add("hidden"))
);
$$(".nav-link").forEach((button) =>
  button.addEventListener("click", () => setView(button.dataset.view))
);
$("#slot-date").addEventListener("change", loadSlots);
$("#search-input").addEventListener("input", () => {
  clearTimeout(window.searchTimer);
  window.searchTimer = setTimeout(loadDoctors, 300);
});
$("#branch-filter").addEventListener("change", loadDoctors);
$("#clear-filters").addEventListener("click", () => {
  $("#search-input").value = "";
  $("#branch-filter").value = "";
  loadDoctors();
});
$("#today-chip").textContent = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date());

setUser(state.user);
goHome(); // setView внутри сам грузит нужный раздел (каталог/расписание/консоль)
if (state.user?.role === "patient") loadAppointments(); // счётчик записей в шапке
