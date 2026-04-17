/* global io */

function initLeaderboardTabs() {
  const tabStreak = document.getElementById("tab-streak");
  const tabPr = document.getElementById("tab-pr");
  const panelStreak = document.getElementById("panel-streak");
  const panelPr = document.getElementById("panel-pr");
  if (!tabStreak || !tabPr || !panelStreak || !panelPr) return;

  const activate = (which) => {
    const streakOn = which === "streak";
    tabStreak.classList.toggle("bg-slate-800", streakOn);
    tabStreak.classList.toggle("text-white", streakOn);
    tabStreak.classList.toggle("shadow-inner", streakOn);
    tabStreak.classList.toggle("text-slate-400", !streakOn);

    tabPr.classList.toggle("bg-slate-800", !streakOn);
    tabPr.classList.toggle("text-white", !streakOn);
    tabPr.classList.toggle("shadow-inner", !streakOn);
    tabPr.classList.toggle("text-slate-400", streakOn);

    panelStreak.classList.toggle("hidden", !streakOn);
    panelPr.classList.toggle("hidden", streakOn);
  };

  tabStreak.addEventListener("click", () => activate("streak"));
  tabPr.addEventListener("click", () => activate("pr"));
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
        <p class="truncate text-xs text-slate-500">${u.workout_style || "Athlete"}</p>
      </div>
    `;
    listEl.appendChild(li);
  });
}

async function refreshGymFeed(statusEl, liveWrap, nameEl, listEl, url) {
  try {
    const res = await fetch(url, { credentials: "same-origin" });
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
      statusEl.textContent = "Geolocation is not supported in this browser.";
      return;
    }
    statusEl.textContent = "Locating you…";
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await fetch("/gym/checkin", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
            }),
          });
          const data = await res.json();
          if (!res.ok || !data.ok) {
            statusEl.textContent = data.error || "Check-in failed.";
            return;
          }
          statusEl.textContent = `Checked in to ${data.gym.name} (${Math.round(data.distance_meters)}m away).`;
          tick();
        } catch {
          statusEl.textContent = "Network error while checking in.";
        }
      },
      () => {
        statusEl.textContent = "Location permission denied or unavailable.";
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });

  btnOut?.addEventListener("click", async () => {
    statusEl.textContent = "Checking out…";
    try {
      const res = await fetch("/gym/checkout", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        statusEl.textContent = "Checkout failed.";
        return;
      }
      statusEl.textContent = "You are checked out.";
      tick();
    } catch {
      statusEl.textContent = "Network error while checking out.";
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

document.addEventListener("DOMContentLoaded", () => {
  initLeaderboardTabs();
  initLeaderboardSocket();
  initGymFeed();
  initPrToast();
});
