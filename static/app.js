/* global io */

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function initLeaderboardTabs() {
  const tabFriends = document.getElementById("tab-friends");
  const tabChallenge = document.getElementById("tab-challenge");
  const tabSuggested = document.getElementById("tab-suggested");
  const panelFriends = document.getElementById("panel-friends");
  const panelChallenge = document.getElementById("panel-challenge");
  const panelSuggested = document.getElementById("panel-suggested");
  if (!tabFriends || !tabChallenge || !tabSuggested || !panelFriends || !panelChallenge || !panelSuggested) {
    return;
  }

  const tabs = [
    { id: "friends", tab: tabFriends, panel: panelFriends },
    { id: "challenge", tab: tabChallenge, panel: panelChallenge },
    { id: "suggested", tab: tabSuggested, panel: panelSuggested },
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
  const initial = (root && root.dataset.activeTab) || "friends";
  activate(["friends", "challenge", "suggested"].includes(initial) ? initial : "friends");

  tabFriends.addEventListener("click", () => activate("friends"));
  tabChallenge.addEventListener("click", () => activate("challenge"));
  tabSuggested.addEventListener("click", () => activate("suggested"));
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

async function sharePlainText(text) {
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

async function shareTitleTextAndUrl(title, text, url, btn) {
  const shareUrl = url || window.location.href;
  const combined = `${text}\n${shareUrl}`;
  const defaultLabel = (btn && btn.textContent && btn.textContent.trim()) || "Share";
  if (navigator.share) {
    try {
      await navigator.share({
        title: title || "GymLink",
        text: text || "",
        url: shareUrl,
      });
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return;
    }
  }
  const copied = await copyToClipboard(combined);
  if (copied && btn) {
    btn.textContent = "Copied!";
    setTimeout(() => {
      btn.textContent = defaultLabel;
    }, 2000);
  } else if (!copied) {
    prompt("Copy:", combined);
  }
}

function initGymlinkSharePr() {
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest(".gymlink-share-pr");
    if (!btn) return;
    const weight = btn.getAttribute("data-weight");
    const exercise = btn.getAttribute("data-exercise");
    const text = buildPrShareText(weight, exercise);
    void sharePlainText(text);
  });
}

function initGymlinkFeedShare() {
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest(".gymlink-feed-share");
    if (!btn) return;
    const title = btn.getAttribute("data-title") || "GymLink";
    const text = btn.getAttribute("data-text") || "";
    const url = btn.getAttribute("data-url") || "";
    void shareTitleTextAndUrl(title, text, url, btn);
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
    let rh = 8;
    let rm = 0;
    try {
      rh = parseInt(document.body.dataset.reminderHour || "8", 10);
      rm = parseInt(document.body.dataset.reminderMinute || "0", 10);
    } catch {
      rh = 8;
      rm = 0;
    }
    if (Number.isNaN(rh) || rh < 0 || rh > 23) rh = 8;
    if (Number.isNaN(rm) || rm < 0 || rm > 59) rm = 0;
    const nowM = now.getHours() * 60 + now.getMinutes();
    const targetM = rh * 60 + rm;
    if (nowM < targetM || nowM > targetM + 5) return;
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

function friendSuggestAvatarUrl(photoUrl) {
  const p = photoUrl == null ? "" : String(photoUrl).trim();
  if (!p) return "";
  if (/^https?:\/\//i.test(p)) return p;
  if (p.startsWith("/uploads/")) return appUrl(p);
  if (!p.startsWith("/") && !p.includes("/")) return appUrl("/uploads/" + p);
  return p;
}

function initFriendUsernameAutocomplete() {
  const root = document.querySelector("[data-friend-username-autocomplete]");
  if (!root) return;
  const url = root.getAttribute("data-suggest-url");
  const input = root.querySelector("[data-friend-handle-input]");
  let list = root.querySelector("[data-friend-suggestions]");
  if (!url || !input || !list) return;

  let hideTimer = null;
  let fetchTimer = null;
  let lastController = null;

  const hide = () => {
    list.classList.add("hidden");
    list.innerHTML = "";
  };

  const looksLikeEmailForSuggest = (raw) => {
    const i = raw.indexOf("@");
    if (i < 0) return false;
    if (i !== 0) return true;
    return (raw.match(/@/g) || []).length !== 1;
  };

  const runFetch = async () => {
    const raw = input.value.trim();
    if (raw.length < 2 || looksLikeEmailForSuggest(raw)) {
      hide();
      return;
    }
    if (lastController) lastController.abort();
    lastController = new AbortController();
    list.innerHTML =
      '<li class="px-3 py-2 text-xs text-slate-500" role="presentation">Searching…</li>';
    list.classList.remove("hidden");
    try {
      const params = new URLSearchParams({ q: raw });
      const res = await fetch(`${url}?${params}`, {
        credentials: "same-origin",
        signal: lastController.signal,
      });
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      const data = ct.includes("application/json") ? await res.json() : {};
      if (!res.ok || !data.ok) throw new Error("bad");
      const rows = data.users || [];
      list.innerHTML = "";
      if (!rows.length) {
        const li = document.createElement("li");
        li.className = "px-3 py-2 text-xs text-slate-500";
        li.setAttribute("role", "presentation");
        li.textContent = "No matching usernames — try email or another spelling.";
        list.appendChild(li);
        list.classList.remove("hidden");
        return;
      }
      rows.forEach((row) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        li.className =
          "flex cursor-pointer items-center gap-2 border-b border-slate-800/80 px-3 py-2 last:border-0 hover:bg-slate-900";
        const av = friendSuggestAvatarUrl(row.photo_url || "");
        const imgHtml = av
          ? `<img src="${escapeHtml(av)}" alt="" class="h-9 w-9 shrink-0 rounded-full border border-slate-800 object-cover" loading="lazy">`
          : `<span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-xs text-slate-500">?</span>`;
        li.innerHTML = `${imgHtml}<div class="min-w-0 flex-1"><div class="truncate text-sm font-medium text-white">${escapeHtml(row.name)}</div><div class="truncate font-mono text-[11px] text-brand-500/90">@${escapeHtml(row.username)}</div></div>`;
        const pick = (e) => {
          e.preventDefault();
          clearTimeout(hideTimer);
          input.value = "@" + String(row.username || "").trim();
          hide();
          input.dispatchEvent(new Event("input", { bubbles: true }));
        };
        li.addEventListener("pointerdown", pick);
        list.appendChild(li);
      });
      list.classList.remove("hidden");
    } catch (e) {
      if (e && e.name === "AbortError") return;
      hide();
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
    hideTimer = setTimeout(hide, 200);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  document.addEventListener("click", (e) => {
    if (!root.contains(e.target)) hide();
  });
}

function fmtPacific(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      dateStyle: "medium",
      timeStyle: "short",
    }).format(d);
  } catch {
    return iso;
  }
}

function flashChatBubble(bubble) {
  if (!bubble) return;
  bubble.classList.add("gymlink-msg-highlight");
  setTimeout(() => bubble.classList.remove("gymlink-msg-highlight"), 1200);
}

function chatMaxMsgId(box) {
  let max = 0;
  box.querySelectorAll("[data-msg-id]").forEach((n) => {
    const v = parseInt(n.getAttribute("data-msg-id"), 10);
    if (!Number.isNaN(v)) max = Math.max(max, v);
  });
  return max;
}

function initDmChatPage() {
  const root = document.getElementById("dm-chat-root");
  const box = document.getElementById("dm-messages");
  const form = document.getElementById("dm-send-form");
  if (!root || !box || !form) return;

  box.querySelectorAll(".dm-msg-time[data-utc]").forEach((el) => {
    el.textContent = fmtPacific(el.getAttribute("data-utc"));
  });

  const mid = parseInt(root.getAttribute("data-match-id"), 10);
  const meId = parseInt(root.getAttribute("data-me-id"), 10);
  const pollUrl = root.getAttribute("data-poll-url") || "";

  function appendDmMsg(payload) {
    const wrap = document.createElement("div");
    wrap.className = `dm-msg flex ${payload.sender_id === meId ? "justify-end" : "justify-start"}`;
    wrap.setAttribute("data-msg-id", String(payload.id));
    const inner = document.createElement("div");
    inner.className =
      "dm-msg-bubble max-w-[80%] rounded-2xl px-3 py-2 text-sm " +
      (payload.sender_id === meId ? "bg-brand-600 text-white" : "bg-slate-800 text-slate-100");
    inner.innerHTML =
      '<p class="dm-msg-body"></p><p class="dm-msg-time mt-1 text-[10px] opacity-70" data-utc=""></p>';
    inner.querySelector(".dm-msg-body").textContent = payload.content || "";
    const te = inner.querySelector(".dm-msg-time");
    te.setAttribute("data-utc", payload.sent_at || "");
    te.textContent = fmtPacific(payload.sent_at || "");
    wrap.appendChild(inner);
    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
    if (payload.sender_id !== meId) flashChatBubble(inner);
  }

  try {
    if (typeof io !== "undefined") {
      const socket = io({ transports: ["websocket", "polling"] });
      socket.on("dm_message", (payload) => {
        if (!payload || payload.match_id !== mid) return;
        if (box.querySelector(`[data-msg-id="${payload.id}"]`)) return;
        appendDmMsg(payload);
      });
    }
  } catch {
    /* ignore */
  }

  if (pollUrl) {
    setInterval(async () => {
      try {
        const after = chatMaxMsgId(box);
        const res = await fetch(`${pollUrl}?after=${encodeURIComponent(String(after))}`, {
          credentials: "same-origin",
        });
        const data = await res.json().catch(() => null);
        if (!data || !data.ok || !Array.isArray(data.messages)) return;
        data.messages.forEach((m) => {
          if (!box.querySelector(`[data-msg-id="${m.id}"]`)) appendDmMsg(m);
        });
      } catch {
        /* ignore */
      }
    }, 10000);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const inp = form.querySelector('input[name="content"]');
    const txt = ((inp && inp.value) || "").trim();
    if (!txt) return;
    try {
      const res = await fetch(window.location.pathname, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => null);
      if (data && data.ok) inp.value = "";
    } catch {
      /* ignore */
    }
  });
}

function initGroupChatPage() {
  const root = document.getElementById("gc-chat-root");
  const box = document.getElementById("gc-messages");
  const form = document.getElementById("gc-send-form");
  const gear = document.getElementById("gc-gear-btn");
  const menu = document.getElementById("gc-settings-menu");
  if (gear && menu) {
    gear.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const open = !menu.classList.contains("hidden");
      if (open) {
        menu.classList.add("hidden");
        gear.setAttribute("aria-expanded", "false");
      } else {
        menu.classList.remove("hidden");
        gear.setAttribute("aria-expanded", "true");
      }
    });
    document.addEventListener("click", () => {
      menu.classList.add("hidden");
      gear.setAttribute("aria-expanded", "false");
    });
    menu.addEventListener("click", (ev) => {
      ev.stopPropagation();
    });
  }
  if (!root || !box || !form) return;

  box.querySelectorAll(".gc-msg-time[data-utc]").forEach((el) => {
    el.textContent = fmtPacific(el.getAttribute("data-utc"));
  });

  const gid = parseInt(root.getAttribute("data-group-id"), 10);
  const meId = parseInt(root.getAttribute("data-me-id"), 10);
  const pollUrl = root.getAttribute("data-poll-url") || "";

  function appendGcMsg(payload) {
    const wrap = document.createElement("div");
    wrap.className = `gc-msg flex ${payload.sender_id === meId ? "justify-end" : "justify-start"}`;
    wrap.setAttribute("data-msg-id", String(payload.id));
    const inner = document.createElement("div");
    inner.className =
      "gc-msg-bubble max-w-[85%] rounded-2xl px-3 py-2 text-sm " +
      (payload.sender_id === meId ? "bg-brand-600 text-white" : "bg-slate-800 text-slate-100");
    const who =
      payload.sender_id !== meId && payload.sender_username
        ? `<p class="mb-1 text-[10px] font-semibold text-brand-400/90">@${escapeHtml(String(payload.sender_username))}</p>`
        : payload.sender_id !== meId
          ? '<p class="mb-1 text-[10px] font-semibold text-brand-400/90">Member</p>'
          : "";
    inner.innerHTML =
      who + '<p class="gc-msg-body"></p><p class="gc-msg-time mt-1 text-[10px] opacity-70" data-utc=""></p>';
    inner.querySelector(".gc-msg-body").textContent = payload.content || "";
    const te = inner.querySelector(".gc-msg-time");
    te.setAttribute("data-utc", payload.sent_at || "");
    te.textContent = fmtPacific(payload.sent_at || "");
    wrap.appendChild(inner);
    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
    if (payload.sender_id !== meId) flashChatBubble(inner);
  }

  try {
    if (typeof io !== "undefined") {
      const socket = io({ transports: ["websocket", "polling"] });
      socket.on("group_message", (payload) => {
        if (!payload || payload.group_id !== gid) return;
        if (box.querySelector(`[data-msg-id="${payload.id}"]`)) return;
        appendGcMsg(payload);
      });
    }
  } catch {
    /* ignore */
  }

  if (pollUrl) {
    setInterval(async () => {
      try {
        const after = chatMaxMsgId(box);
        const res = await fetch(`${pollUrl}?after=${encodeURIComponent(String(after))}`, {
          credentials: "same-origin",
        });
        const data = await res.json().catch(() => null);
        if (!data || !data.ok || !Array.isArray(data.messages)) return;
        data.messages.forEach((m) => {
          if (!box.querySelector(`[data-msg-id="${m.id}"]`)) appendGcMsg(m);
        });
      } catch {
        /* ignore */
      }
    }, 10000);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const inp = form.querySelector('input[name="content"]');
    const txt = ((inp && inp.value) || "").trim();
    if (!txt) return;
    try {
      const res = await fetch(window.location.pathname, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => null);
      if (data && data.ok) inp.value = "";
    } catch {
      /* ignore */
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initLeaderboardTabs();
  initLeaderboardSocket();
  initGymFeed();
  initPrToast();
  initSchoolAutocomplete();
  initFriendUsernameAutocomplete();
  initGymlinkSharePr();
  initGymlinkFeedShare();
  initDmChatPage();
  initGroupChatPage();
  initWorkoutDayReminders();
  initNotificationEnable();
});
