function todayStr() {
  const d = new Date();
  const tz = d.getTimezoneOffset() * 60000;
  return new Date(d - tz).toISOString().slice(0, 10);
}

function isWorkdayJS(dateStr) {
  const wd = new Date(dateStr + "T00:00:00").getDay();
  return wd !== 0 && wd !== 6;
}

function addDays(dateStr, n) {
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function debounce(fn, delay) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
}

function pseudoHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h * 31 + str.charCodeAt(i)) >>> 0;
  }
  return h.toString(16).padStart(7, "0").slice(0, 7);
}

const TODAY = todayStr();
let currentDay = null;
let locked = false;
let historyOffset = 0;
const HISTORY_LIMIT = 20;

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.status;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

// ---------- save ----------

async function saveDay() {
  if (locked) return;
  const payload = {
    todos: currentDay.todos,
    standup: currentDay.standup,
    practice: currentDay.practice,
    reflection: currentDay.reflection,
  };
  try {
    currentDay = await api(`/api/days/${TODAY}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    if (e.status === 423) {
      locked = true;
      renderLockState();
    }
  }
}

const debouncedSave = debounce(saveDay, 800);

// ---------- todos ----------

function renderTodos() {
  const list = document.getElementById("todoList");
  list.innerHTML = "";
  currentDay.todos.forEach((t) => {
    const row = document.createElement("div");
    row.className = "todo-item" + (t.done ? " done" : "");
    row.innerHTML = `
      <input type="checkbox" ${t.done ? "checked" : ""} data-id="${t.id}">
      <span class="todo-text">${escapeHtml(t.text)}</span>
      <button class="todo-del" data-id="${t.id}" type="button">x</button>
    `;
    list.appendChild(row);
  });
  list.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", (e) => {
      const id = e.target.dataset.id;
      const item = currentDay.todos.find((t) => t.id === id);
      item.done = e.target.checked;
      renderTodos();
      saveDay();
    });
  });
  list.querySelectorAll(".todo-del").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const id = e.target.dataset.id;
      currentDay.todos = currentDay.todos.filter((t) => t.id !== id);
      renderTodos();
      saveDay();
    });
  });
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function wireTodoForm() {
  document.getElementById("todoForm").addEventListener("submit", (e) => {
    e.preventDefault();
    if (locked) return;
    const input = document.getElementById("todoInput");
    const text = input.value.trim();
    if (!text) return;
    currentDay.todos.push({ id: crypto.randomUUID(), text, done: false });
    input.value = "";
    renderTodos();
    saveDay();
  });
}

// ---------- standup ----------

function renderStandup() {
  document.getElementById("su_assigned").value = currentDay.standup.assigned;
  document.getElementById("su_completed").value = currentDay.standup.completed;
  document.getElementById("su_missed").value = currentDay.standup.missed;
  document.getElementById("su_extra").value = currentDay.standup.extra;
  document.getElementById("su_focus").value = currentDay.standup.focus;
  document.getElementById("out_simple").value = currentDay.standup.generated.simple;
  document.getElementById("out_detailed").value = currentDay.standup.generated.detailed;
  document.getElementById("out_ideal").value = currentDay.standup.generated.ideal;
}

function wireStandupFields() {
  const map = {
    su_assigned: "assigned",
    su_completed: "completed",
    su_missed: "missed",
    su_extra: "extra",
    su_focus: "focus",
  };
  Object.entries(map).forEach(([elId, key]) => {
    document.getElementById(elId).addEventListener("input", (e) => {
      currentDay.standup[key] = e.target.value;
      debouncedSave();
    });
  });

  const outMap = { out_simple: "simple", out_detailed: "detailed", out_ideal: "ideal" };
  Object.entries(outMap).forEach(([elId, key]) => {
    document.getElementById(elId).addEventListener("input", (e) => {
      currentDay.standup.generated[key] = e.target.value;
      debouncedSave();
    });
  });

  document.querySelectorAll("#outputTabs .tab").forEach((tabBtn) => {
    tabBtn.addEventListener("click", () => {
      document.querySelectorAll("#outputTabs .tab").forEach((b) => b.classList.remove("active"));
      tabBtn.classList.add("active");
      ["simple", "detailed", "ideal"].forEach((name) => {
        document.getElementById(`out_${name}`).hidden = name !== tabBtn.dataset.tab;
      });
    });
  });

  document.getElementById("generateBtn").addEventListener("click", generateStandup);
}

async function generateStandup() {
  const status = document.getElementById("generateStatus");
  const btn = document.getElementById("generateBtn");
  status.textContent = "generating...";
  btn.disabled = true;
  try {
    const gen = await api("/api/standup/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assigned: currentDay.standup.assigned,
        completed: currentDay.standup.completed,
        missed: currentDay.standup.missed,
        extra: currentDay.standup.extra,
        focus: currentDay.standup.focus,
        today_todos: currentDay.todos,
      }),
    });
    currentDay.standup.generated = gen;
    renderStandup();
    status.textContent = "generated.";
    await saveDay();
  } catch (e) {
    status.textContent = `error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

function prefillStandupIfEmpty(ctx) {
  let changed = false;
  if (!currentDay.standup.assigned && (ctx.assigned_today || ctx.backlog)) {
    currentDay.standup.assigned = ctx.assigned_today || ctx.backlog;
    changed = true;
  }
  if (!currentDay.standup.completed && ctx.completed.length) {
    currentDay.standup.completed = ctx.completed.join("; ");
    changed = true;
  }
  if (!currentDay.standup.missed && ctx.missed.length) {
    currentDay.standup.missed = ctx.missed.join("; ");
    changed = true;
  }
  if (changed) saveDay();
}

// ---------- practice ----------

function renderPractice() {
  document.getElementById("practiceDone").checked = currentDay.practice.done;
  document.getElementById("practiceNote").value = currentDay.practice.note;
}

function wirePractice() {
  document.getElementById("practiceDone").addEventListener("change", (e) => {
    currentDay.practice.done = e.target.checked;
    saveDay();
    refreshPractice();
    refreshGraph();
  });
  document.getElementById("practiceNote").addEventListener("input", (e) => {
    currentDay.practice.note = e.target.value;
    debouncedSave();
  });
}

async function refreshPractice() {
  const r = await api(`/api/practice/rolling?as_of=${TODAY}`);
  document.getElementById("practiceWeek").textContent = `${r.count}/${r.days}`;
}

// ---------- reflection ----------

function renderReflection() {
  document.getElementById("rf_done").value = currentDay.reflection.done;
  document.getElementById("rf_missed").value = currentDay.reflection.missed;
  document.getElementById("rf_learned").value = currentDay.reflection.learned;
  document.getElementById("rf_better").value = currentDay.reflection.better;
  document.getElementById("rf_assigned").value = currentDay.reflection.assigned;
  document.getElementById("rf_backlog").value = currentDay.reflection.backlog;
}

function wireReflection() {
  const map = {
    rf_done: "done",
    rf_missed: "missed",
    rf_learned: "learned",
    rf_better: "better",
    rf_assigned: "assigned",
    rf_backlog: "backlog",
  };
  Object.entries(map).forEach(([elId, key]) => {
    document.getElementById(elId).addEventListener("input", (e) => {
      currentDay.reflection[key] = e.target.value;
      debouncedSave();
    });
  });

  document.getElementById("wrapBtn").addEventListener("click", async () => {
    if (!confirm("This locks today's entry permanently. Continue?")) return;
    try {
      currentDay = await api(`/api/days/${TODAY}/wrap`, { method: "POST" });
      locked = true;
      renderLockState();
      refreshStreak();
      refreshGraph();
      loadHistory(true);
    } catch (e) {
      alert(`could not wrap day: ${e.message}`);
    }
  });
}

// ---------- lock state ----------

function renderLockState() {
  document.getElementById("lockedBanner").hidden = !locked;
  document
    .querySelectorAll(".main-col input, .main-col textarea, .main-col button")
    .forEach((el) => {
      el.disabled = locked;
    });
}

// ---------- streak ----------

async function refreshStreak() {
  const r = await api(`/api/streak?as_of=${TODAY}`);
  document.getElementById("streakCount").textContent = r.streak + (currentDay.completed_day ? 1 : 0);
}

// ---------- graph ----------

function activityLevel(dateStr, record) {
  const workday = record ? record.is_workday : isWorkdayJS(dateStr);
  if (!workday) return "weekend";
  if (!record) return "none";
  const hasActivity =
    record.todos.length > 0 ||
    record.standup.assigned ||
    record.standup.completed ||
    record.standup.focus ||
    record.reflection.done ||
    record.practice.done;
  if (!record.completed_day) return hasActivity ? "some" : "none";
  const total = record.todos.length;
  const done = record.todos.filter((t) => t.done).length;
  const ratio = total === 0 ? 1 : done / total;
  return ratio >= 0.7 ? "high" : "low";
}

async function refreshGraph() {
  const start = addDays(TODAY, -34);
  const rows = await api(`/api/days?start=${start}&end=${TODAY}`);
  const byDate = {};
  rows.forEach((r) => (byDate[r.date] = r));

  const graph = document.getElementById("graph");
  graph.innerHTML = "";
  for (let i = -34; i <= 0; i++) {
    const d = addDays(TODAY, i);
    const record = d === TODAY ? currentDay : byDate[d];
    const level = activityLevel(d, record);
    const cell = document.createElement("div");
    cell.className = `graph-cell ${level}`;
    cell.title = `${d}: ${level}`;
    graph.appendChild(cell);
  }
}

// ---------- history ----------

function summarize(record) {
  const done = record.todos.filter((t) => t.done).length;
  const parts = [`${done}/${record.todos.length} todos`];
  if (record.completed_day) parts.push("wrapped");
  if (record.practice.done) parts.push("practiced");
  return parts.join(" · ");
}

function appendHistoryEntry(record) {
  const div = document.createElement("div");
  div.className = "history-entry";
  const hash = pseudoHash(record.date + record.updated_at);
  div.innerHTML = `
    <span class="hash">${hash}</span><span class="hdate">${record.date}</span>
    <span class="summary">${summarize(record)}</span>
  `;
  div.addEventListener("click", () => {
    let expanded = div.querySelector(".expanded");
    if (expanded) {
      expanded.remove();
      return;
    }
    expanded = document.createElement("div");
    expanded.className = "expanded";
    const todoLines = record.todos.map((t) => `[${t.done ? "x" : " "}] ${t.text}`).join("\n") || "(none)";
    expanded.textContent =
      `todos:\n${todoLines}\n\n` +
      `standup (ideal): ${record.standup.generated.ideal || "(none)"}\n\n` +
      `reflection:\n` +
      `  done: ${record.reflection.done || "-"}\n` +
      `  missed: ${record.reflection.missed || "-"}\n` +
      `  learned: ${record.reflection.learned || "-"}\n` +
      `  better: ${record.reflection.better || "-"}`;
    div.appendChild(expanded);
  });
  document.getElementById("historyLog").appendChild(div);
}

async function loadHistory(reset) {
  if (reset) {
    historyOffset = 0;
    document.getElementById("historyLog").innerHTML = "";
    document.getElementById("loadMoreBtn").disabled = false;
  }
  const rows = await api(`/api/history?limit=${HISTORY_LIMIT}&offset=${historyOffset}`);
  rows.forEach(appendHistoryEntry);
  historyOffset += rows.length;
  if (rows.length < HISTORY_LIMIT) document.getElementById("loadMoreBtn").disabled = true;
}

// ---------- maintenance ----------

function wireMaintenance() {
  document.getElementById("archiveBtn").addEventListener("click", async () => {
    const cutoff = document.getElementById("archiveCutoff").value;
    const status = document.getElementById("maintenanceStatus");
    if (!cutoff) {
      status.textContent = "pick a cutoff date first";
      return;
    }
    try {
      const r = await api("/api/maintenance/archive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cutoff_date: cutoff }),
      });
      status.textContent = `archived ${r.archived_count} entries`;
      refreshGraph();
      loadHistory(true);
    } catch (e) {
      status.textContent = `error: ${e.message}`;
    }
  });

  document.getElementById("deleteArchivedBtn").addEventListener("click", async () => {
    if (!confirm("Permanently delete all archived entries? This cannot be undone.")) return;
    const status = document.getElementById("maintenanceStatus");
    try {
      const r = await api("/api/maintenance/archived", { method: "DELETE" });
      status.textContent = `permanently deleted ${r.deleted_count} entries`;
    } catch (e) {
      status.textContent = `error: ${e.message}`;
    }
  });

  document.getElementById("loadMoreBtn").addEventListener("click", () => loadHistory(false));
}

// ---------- init ----------

function renderAll() {
  renderTodos();
  renderStandup();
  renderPractice();
  renderReflection();
}

async function init() {
  document.getElementById("todayDate").textContent = TODAY;
  currentDay = await api(`/api/days/${TODAY}`);
  locked = currentDay.completed_day;

  const ctx = await api(`/api/days/${TODAY}/context`);
  prefillStandupIfEmpty(ctx);

  renderAll();
  renderLockState();

  wireTodoForm();
  wireStandupFields();
  wirePractice();
  wireReflection();
  wireMaintenance();

  refreshStreak();
  refreshPractice();
  refreshGraph();
  loadHistory(true);
}

init();
