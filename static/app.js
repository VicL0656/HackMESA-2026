/* global io */

function initLeaderboardTabs() {
  const tabStreak = document.getElementById("tab-streak");
  const tabPr = document.getElementById("tab-pr");
  const tabOutdoor = document.getElementById("tab-outdoor");
  const panelStreak = document.getElementById("panel-streak");
  const panelPr = document.getElementById("panel-pr");
  const panelOutdoor = document.getElementById("panel-outdoor");
  if (!tabStreak || !tabPr || !tabOutdoor || !panelStreak || !panelPr || !panelOutdoor) return;

  const tabs = [
    { id: "streak", tab: tabStreak, panel: panelStreak },
    { id: "pr", tab: tabPr, panel: panelPr },
    { id: "outdoor", tab: tabOutdoor, panel: panelOutdoor },
  ];

  const activate = (which) => {
    tabs.forEach(({ id, tab, panel }) => {
      const on = id === which;
      tab.classList.toggle("bg-slate-800", on);
      tab.classList.toggle("text-white", on);
      tab.classList.toggle("shadow-inner", on);
      tab.classList.toggle("text-slate-400", !on);
      panel.classList.toggle("hidden", !on);
    });
  };

  const root = document.getElementById("leaderboard-root");
  const initial = (root && root.dataset.activeTab) || "streak";
  activate(["streak", "pr", "outdoor"].includes(initial) ? initial : "streak");

  tabStreak.addEventListener("click", () => activate("streak"));
  tabPr.addEventListener("click", () => activate("pr"));
  tabOutdoor.addEventListener("click", () => activate("outdoor"));
}

function initLeaderboardSocket() {
  if (!document.getElementById("leaderboard-root")) return;
  const socket = io({ transports: ["websocket", "polling"] });
  socket.on("leaderboard_update", () => {
    window.location.reload();
  });
}

function renderGymUsers(listEl, users) {
  listEl.innerHTML = "";
  if (!users.length) {
    const li = document.createElement("li");
    li.className = "rounded-xl border border-dashed border-slate-800 bg-slate-950/40 px-3 py-3 text-sm text-slate-400";
    li.textContent = "No other lifters checked in right now. You are early.";
    listEl.appendChild(li);
    return;
  }
  users.forEach((u) => {
    const li = document.createElement("li");
    li.className = "flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2";
    li.innerHTML = `
      <img src="${u.photo_url}" alt="" class="h-9 w-9 rounded-full border border-slate-800 object-cover" />
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-semibold text-white">${u.name}</p>
        <p class="truncate font-mono text-[11px] text-emerald-400/90">@${u.username || "user"}</p>
        <p class="truncate text-xs text-slate-500">${u.workout_style || "Athlete"}</p>
      </div>
    `;
    listEl.appendChild(li);
  });
}

function appUrl(pathAndQuery) {
  const root =
    typeof window.GYMLINK_SCRIPT_ROOT === "string"
      ? window.GYMLINK_SCRIPT_ROOT.replace(/\/$/, "")
      : "";
  const p = pathAndQuery.startsWith("/") ? pathAndQuery : `/${pathAndQuery}`;
  return `${root}${p}`;
}

function formatDistanceFromApi(data) {
  if (data && typeof data.distance_miles === "number") {
    return `${data.distance_miles} mi`;
  }
  if (data && typeof data.distance_meters === "number") {
    return `${Math.round(data.distance_meters)} m`;
  }
  return "";
}

async function refreshGymFeed(statusEl, liveWrap, nameEl, listEl, url) {
  try {
    const res = await fetch(url, { credentials: "same-origin" });
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (!ct.includes("application/json")) throw new Error("not json");
    const data = await res.json();
    if (!data.ok) throw new Error("bad payload");
    if (!data.checked_in) {
      liveWrap.classList.add("hidden");
      if (statusEl) statusEl.textContent = "";
      return;
    }
    liveWrap.classList.remove("hidden");
    nameEl.textContent = data.gym.name;
    renderGymUsers(listEl, data.users || []);
  } catch {
    if (statusEl) statusEl.textContent = "Could not refresh gym feed.";
  }
}

function initGymFeed() {
  const meta = document.getElementById("gym-feed-page");
  if (!meta) return;
  const url = meta.dataset.feedUrl;
  const checkinUrl = meta.dataset.checkinUrl || appUrl("/gym/checkin");
  const checkoutUrl = meta.dataset.checkoutUrl || appUrl("/gym/checkout");
  const statusEl = document.getElementById("geo-status");
  const liveWrap = document.getElementById("gym-live");
  const nameEl = document.getElementById("gym-name");
  const listEl = document.getElementById("gym-users");
  const btnIn = document.getElementById("btn-checkin");
  const btnOut = document.getElementById("btn-checkout");
  if (!url || !liveWrap || !nameEl || !listEl) return;

  const tick = () => refreshGymFeed(statusEl, liveWrap, nameEl, listEl, url);
  tick();
  setInterval(tick, 8000);

  btnIn?.addEventListener("click", () => {
    if (!navigator.geolocation) {
      if (statusEl) statusEl.textContent = "Geolocation is not supported in this browser.";
      return;
    }
    if (statusEl) statusEl.textContent = "Locating you…";
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await fetch(checkinUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
            }),
          });
          const ct = (res.headers.get("content-type") || "").toLowerCase();
          const data = ct.includes("application/json") ? await res.json() : {};
          if (!res.ok || !data.ok) {
            let msg = data.error || "Check-in failed.";
            if (data.nearest_gym && typeof data.nearest_miles === "number") {
              msg += ` Closest: ${data.nearest_gym.name} (~${data.nearest_miles} mi).`;
            } else if (data.nearest_gym && typeof data.nearest_meters === "number") {
              msg += ` Closest: ${data.nearest_gym.name} (~${Math.round(data.nearest_meters)} m).`;
            }
            if (data.hint) {
              msg += ` ${data.hint}`;
            }
            if (statusEl) statusEl.textContent = msg;
            return;
          }
          const dist = formatDistanceFromApi(data);
          if (statusEl) {
            statusEl.textContent = dist
              ? `Checked in to ${data.gym.name} (${dist} away).`
              : `Checked in to ${data.gym.name}.`;
          }
          tick();
        } catch {
          if (statusEl) statusEl.textContent = "Network error while checking in.";
        }
      },
      (err) => {
        const why =
          err && err.code === 1
            ? "Location permission denied."
            : err && err.code === 2
              ? "Position unavailable."
              : err && err.code === 3
                ? "Location request timed out."
                : "Location permission denied or unavailable.";
        if (statusEl) statusEl.textContent = why;
      },
      { enableHighAccuracy: false, timeout: 25000, maximumAge: 120000 },
    );
  });

  btnOut?.addEventListener("click", async () => {
    if (statusEl) statusEl.textContent = "Checking out…";
    try {
      const res = await fetch(checkoutUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      const data = ct.includes("application/json") ? await res.json() : {};
      if (!res.ok || !data.ok) {
        if (statusEl) statusEl.textContent = "Checkout failed.";
        return;
      }
      if (statusEl) statusEl.textContent = "You are checked out.";
      tick();
    } catch {
      if (statusEl) statusEl.textContent = "Network error while checking out.";
    }
  });
}

function initPrToast() {
  const toast = document.getElementById("pr-toast");
  if (!toast) return;
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-1", "transition", "duration-700");
    setTimeout(() => toast.remove(), 800);
  }, 4200);
}

function schoolSearchApiUrl(params) {
  return appUrl(`/api/schools?${params}`);
}

function initSchoolAutocomplete() {
  const input = document.querySelector("input[data-school-autocomplete]");
  if (!input) return;
  const root = input.closest("[data-school-autocomplete-root]") || input.parentElement;
  let list = root.querySelector("[data-school-suggestions]");
  if (!list) {
    list = document.createElement("ul");
    list.dataset.schoolSuggestions = "";
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "School suggestions");
    list.className =
      "absolute left-0 right-0 top-full z-[200] mt-1 max-h-60 overflow-y-auto rounded-xl border border-slate-700 bg-slate-950 py-1 text-left shadow-xl hidden";
    root.appendChild(list);
  }

  let hideTimer = null;
  let fetchTimer = null;
  let lastController = null;

  const escapeHtml = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };

  const hide = () => {
    list.classList.add("hidden");
    list.innerHTML = "";
  };

  const showLoading = () => {
    list.innerHTML =
      '<li class="px-3 py-2 text-xs text-slate-500" role="presentation">Searching…</li>';
    list.classList.remove("hidden");
  };

  const render = (rows, emptyMsg) => {
    list.innerHTML = "";
    if (!rows.length) {
      const li = document.createElement("li");
      li.className = "px-3 py-2 text-xs text-slate-500";
      li.textContent = emptyMsg;
      li.setAttribute("role", "presentation");
      list.appendChild(li);
      list.classList.remove("hidden");
      return;
    }
    rows.forEach((row) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.className =
        "cursor-pointer border-b border-slate-800/80 px-3 py-2 last:border-0 hover:bg-slate-900";
      li.innerHTML = `<div class="text-sm font-medium text-white">${escapeHtml(row.name)}</div><div class="text-[11px] text-slate-500">${escapeHtml(row.subtitle || "")}</div>`;
      const pick = (e) => {
        e.preventDefault();
        clearTimeout(hideTimer);
        input.value = row.name;
        hide();
        input.dispatchEvent(new Event("change", { bubbles: true }));
      };
      li.addEventListener("pointerdown", pick);
      list.appendChild(li);
    });
    list.classList.remove("hidden");
  };

  const runFetch = async () => {
    const q = input.value.trim();
    if (q.length < 2) {
      hide();
      return;
    }
    if (lastController) lastController.abort();
    lastController = new AbortController();
    showLoading();
    try {
      const params = new URLSearchParams({ q, limit: "25" });
      const url = schoolSearchApiUrl(params);
      const res = await fetch(url, {
        credentials: "same-origin",
        signal: lastController.signal,
      });
      let data;
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (ct.includes("application/json")) {
        data = await res.json();
      } else {
        await res.text();
        throw new Error(`HTTP ${res.status}`);
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rows = data.results || [];
      if ((data.total_loaded || 0) === 0) {
        render([], "School list not installed. Run: py -3 scripts/build_us_institutions.py");
        return;
      }
      render(rows, "No schools match. Try another spelling.");
    } catch (e) {
      if (e.name === "AbortError") return;
      render([], "Could not load schools. Check your connection.");
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(fetchTimer);
    fetchTimer = setTimeout(runFetch, 220);
  });

  input.addEventListener("focus", () => {
    if (input.value.trim().length >= 2) runFetch();
  });

  input.addEventListener("blur", () => {
    hideTimer = setTimeout(hide, 280);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  document.addEventListener("click", (e) => {
    if (!root.contains(e.target)) hide();
  });
}

function buildPrShareText(weight, exercise) {
  const w = typeof weight === "number" ? weight : parseFloat(String(weight), 10);
  const ws = Number.isFinite(w) ? w.toFixed(1) : String(weight ?? "").trim();
  const ex = (exercise == null ? "" : String(exercise)).trim() || "my lift";
  return `I just hit a ${ws} PR on ${ex} on GymLink 💪`;
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      return true;
    } catch {
      return false;
    }
  }
}

async function shareOrCopyPr(text) {
  if (navigator.share) {
    try {
      await navigator.share({ text });
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return;
    }
  }
  await copyToClipboard(text);
}

function initGymlinkSharePr() {
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest(".gymlink-share-pr");
    if (!btn) return;
    const weight = btn.getAttribute("data-weight");
    const exercise = btn.getAttribute("data-exercise");
    const text = buildPrShareText(weight, exercise);
    shareOrCopyPr(text);
  });
}

function pyWeekdayFromLocalDate(d) {
  const js = d.getDay();
  return js === 0 ? 6 : js - 1;
}

function initWorkoutDayReminders() {
  const raw = document.body.dataset.workoutDays;
  if (!raw) return;
  let days;
  try {
    days = JSON.parse(raw);
  } catch {
    return;
  }
  if (!Array.isArray(days) || !days.length) return;
  const set = new Set(days.map((x) => parseInt(x, 10)).filter((n) => n >= 0 && n <= 6));

  const tick = async () => {
    if (typeof Notification === "undefined") return;
    if (Notification.permission !== "granted") return;
    const now = new Date();
    if (now.getHours() !== 8 || now.getMinutes() > 5) return;
    if (!set.has(pyWeekdayFromLocalDate(now))) return;
    const key = `gymlink_remind_${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`;
    if (sessionStorage.getItem(key)) return;
    let logged = true;
    try {
      const res = await fetch(appUrl("/api/me/workout-today"), { credentials: "same-origin" });
      const data = await res.json();
      logged = Boolean(data && data.logged);
    } catch {
      return;
    }
    if (logged) {
      sessionStorage.setItem(key, "1");
      return;
    }
    sessionStorage.setItem(key, "1");
    try {
      new Notification("GymLink", {
        body: "You have not logged a workout or rest day yet — tap to open GymLink.",
        tag: "gymlink-daily",
      });
    } catch {
      /* ignore */
    }
  };

  setInterval(tick, 60 * 1000);
  tick();
}

function initNotificationEnable() {
  const btn = document.getElementById("gymlink-enable-notifications");
  if (!btn || typeof Notification === "undefined") return;
  btn.addEventListener("click", async () => {
    try {
      const p = await Notification.requestPermission();
      if (p === "granted") btn.textContent = "Notifications on";
      else btn.textContent = "Permission not granted";
    } catch {
      btn.textContent = "Not supported";
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initLeaderboardTabs();
  initLeaderboardSocket();
  initGymFeed();
  initPrToast();
  initSchoolAutocomplete();
  initGymlinkSharePr();
  initWorkoutDayReminders();
  initNotificationEnable();
});
