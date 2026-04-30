# GymLink — Integration lane report

## Scope

This document maps **HTTP routes ↔ Jinja templates ↔ client-side `fetch` / Socket.IO** for the Flask app in this workspace. It covers **form posts** (including JSON POST APIs used from settings and the feed), **session / cookies** (`Flask-Login`), **CSRF posture** (none in codebase), and **environment variables** read at runtime.

Excluded: internal Python-only helpers, SQLAlchemy models except where they affect integration, and deployment wiring beyond env vars referenced in code.

## Work summary

- **Server-rendered UI**: Most screens are full page renders extending `base.html`, which sets `window.GYMLINK_SCRIPT_ROOT` from `request.script_root` and loads `static/app.js` with `defer`.
- **Global client bundle (`static/app.js`)**: Leaderboard tabs + Socket.IO `leaderboard_update` full reload; gym live feed polling + JSON check-in/out; school autocomplete (`GET /api/schools`); friend username suggest (URL from `data-suggest-url`); PR share clipboard; workout-day browser notifications with `GET /api/me/workout-today`.
- **Inline template scripts**: `account_settings.html` calls account JSON APIs for city/OSM gym search; `match_thread.html` / `group_thread.html` poll JSON endpoints and `POST` the same path as the page with `FormData` for new messages.
- **Auth**: `Flask-Login` with optional “remember me”; Flask **`session` cookie** stores login state. No Flask-WTF / CSRF tokens found.
- **Realtime**: `flask-socketio` connects from the CDN client; server joins clients to `user_{id}` rooms; **only leaderboard home** subscribes in `app.js` today (`leaderboard_update`). DM/group emits exist server-side but are not wired in the shared bundle.

## Contracts & interfaces

### Base URL and script root

- **`window.GYMLINK_SCRIPT_ROOT`**: Injected in `base.html` as `request.script_root` JSON. Used by `appUrl()` in `app.js` so the same JS works behind a URL prefix (e.g. reverse proxy).

### Session, cookies, CSRF

| Mechanism | Behavior |
|-----------|----------|
| **Session** | Standard Flask session (signed with `SECRET_KEY`). Used with `Flask-Login` for user id / freshness. |
| **Remember me** | `login_user(..., remember=...)` from register/login forms; `REMEMBER_COOKIE_DURATION` 30 days in `create_app()`. |
| **Production cookies** | If `RAILWAY_PUBLIC_DOMAIN` or `RAILWAY_ENVIRONMENT == production`: `SESSION_COOKIE_SECURE`, `HTTPONLY`, `SAMESITE=Lax`, `ProxyFix` applied. |
| **CSRF** | **Not implemented** (no `flask_wtf`, no CSRF meta or headers). Mutations rely on **same-origin cookie session** only. |

### JSON / fetch endpoints (representative)

| Endpoint | Method | Auth | Called from | Response shape (summary) |
|----------|--------|------|-------------|----------------------------|
| `/gym/feed` | GET | `@login_required` | `feed.html` → `app.js` `refreshGymFeed` | `{ ok, checked_in, gym?, users[] }` |
| `/gym/checkin` | POST JSON | `@login_required` | `app.js` (body: `latitude`, `longitude`) | `{ ok, gym?, distance_* , error?, nearest_*?, hint? }` |
| `/gym/checkout` | POST JSON | `@login_required` | `app.js` | `{ ok }` |
| `/api/schools` | GET | public | `app.js` school autocomplete | `{ results[], total_loaded }` |
| `/api/me/workout-today` | GET | `@login_required` | `app.js` reminder poll | `{ logged: boolean }` |
| `/friends/username-suggest` | GET | `@login_required` | `app.js` (`data-suggest-url` on add-friend UI) | `{ ok, users[] }` |
| `/account/api/city-search` | POST JSON | `@login_required` | `account_settings.html` inline | `{ ok, places[] }` |
| `/account/api/gym-search` | POST JSON | `@login_required` | `account_settings.html` inline | `{ ok, center?, gyms[] }` |
| `/account/api/gym-pick` | POST JSON | `@login_required` | `account_settings.html` inline | `{ ok, gym? }` |
| `/account/api/gym-manual` | POST JSON | `@login_required` | `account_settings.html` inline | `{ ok, ... }` |
| `/matches/<id>/poll` | GET | `@login_required` | `match_thread.html` | `{ ok, messages[] }` |
| `/groups/<id>/poll` | GET | `@login_required` | `group_thread.html` | `{ ok, messages[] }` |

All `fetch` callers observed use **`credentials: "same-origin"`** where applicable.

### Socket.IO (client ↔ server)

- **Client**: `socket.io` CDN in `base.html`; `app.js` uses `io({ transports: ["websocket", "polling"] })` on leaderboard page only.
- **Server connect** (`app.py`): Requires authenticated user or `_user_id` in session; **`join_room(f"user_{uid}")`**.
- **Events**: `leaderboard_update` (handled in `app.js` → full page reload); `dm_message` / `group_message` emitted from `realtime.py` but **not consumed in `app.js`** (threads use HTTP polling).

### Key screens → routes → templates → `app.js` / inline JS

| Screen (product) | Main route(s) | Template | Client integration |
|------------------|---------------|----------|--------------------|
| App entry / redirect | `GET /` → login or leaderboard | — | — |
| Short “log” link | `GET /log` → `/workouts/log` | — | — |
| Register | `GET/POST /register` | `register.html` | `app.js`: `initSchoolAutocomplete` → `/api/schools` |
| Login | `GET/POST /login` | `login.html` | — |
| Logout | `GET /logout` | redirect | — |
| Forgot / reset password | `GET/POST /forgot-password`, `GET/POST /reset-password/<token>` | `forgot_password.html`, `reset_password.html` | — |
| Home (leaderboard) | `GET /leaderboard?tab=&exercise=` | `leaderboard.html` | `app.js`: tabs, `initLeaderboardSocket` → `leaderboard_update` |
| Inbox | `GET /inbox`, `POST /inbox/read/<id>`, `POST /inbox/read-all` | `inbox.html` | Forms only |
| Log workout | `GET/POST /workouts/log`, `POST /workouts/<id>/delete` | `log_workout.html` | — |
| Edit workout | `GET/POST /workouts/<id>/edit` | `edit_workout.html` | — |
| Social feed | `GET /feed` | `feed.html` | `app.js`: `initGymFeed` → `/gym/feed`, `/gym/checkin`, `/gym/checkout` via meta tags |
| Profile | `GET /profile`, many `POST /profile/*` | `profile.html` | Forms; optional `initWorkoutDayReminders` + notifications from `base.html` body `data-*` |
| Connect by handle | `GET/POST /connect/<username>` | `connect.html` | — |
| Add friend (dedicated) | `GET /add-friend`, `POST /friends/add` | `add_friend.html` | `app.js`: `initFriendUsernameAutocomplete` → `/friends/username-suggest` |
| DM thread | `GET/POST /matches/<id>`, `GET /matches/<id>/poll` | `match_thread.html` | Inline: poll + `POST` (FormData, `xhr=1`) |
| Groups | `GET /groups`, `GET/POST /groups/new`, `GET/POST /groups/<id>`, `GET /groups/<id>/poll`, `POST /groups/<id>/leave` | `groups.html`, `group_new.html`, `group_thread.html` | Inline poll + `POST` on group thread |
| Account settings | `GET/POST /account/settings`, `POST /account/delete-account` | `account_settings.html` | Inline: `/account/api/*` JSON; training form posts traditional |
| Outdoor log / history | `GET/POST /outdoor/log`, `GET /outdoor/exercise/<kind>` | `outdoor_log.html`, `outdoor_exercise.html` | — |
| Body weight | `GET/POST /weights/log`, `POST /weights/log/<id>/delete` | `weight_log.html` | — |
| Health | `GET /health` | JSON | — |
| Uploaded media | `GET /uploads/<name>` | — | — |
| 404 | any unknown | `404.html` | — |

### Environment variables (code references)

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing; password reset token HMAC; fallback dev default in code |
| `DATABASE_URL` / `SQLALCHEMY_DATABASE_URI` | SQLAlchemy URI (`postgres://` normalized) |
| `GYM_CHECKIN_MAX_METERS` / `GYM_CHECKIN_MAX_MILES` | GPS match radius for check-in |
| `OVERPASS_API_URL` | OSM Overpass endpoint (gym discovery) |
| `GYMLINK_HTTP_USER_AGENT` | Outbound HTTP identity (Overpass, geocoding, etc.) |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | Optional transactional email |
| `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_ENVIRONMENT` | Triggers secure cookies + `ProxyFix` |
| `GYMLINK_ASYNC_MODE` | Socket.IO `async_mode` (`threading` / `gevent` / `eventlet`) |
| `GYMLINK_INSTITUTIONS_JSON` | Override path for school search JSON |

## Dependencies on other lanes

- **Frontend lane**: `base.html` shell, Tailwind CDN, bottom nav, flash message UI, and any template-only behaviors must stay aligned with `app.js` selectors (`#leaderboard-root`, `#gym-feed-page`, `data-school-autocomplete`, etc.).
- **Backend lane**: Route names (`url_for` targets), JSON response keys (`ok`, `users`, `gyms`, …), and `@login_required` gates define the integration contract; changes to handlers must stay compatible with `app.js` and inline scripts.
- **Database lane**: Session-backed identity and models underpin every authenticated fetch; check-in and feed JSON depend on `CheckIn`, `Gym`, `User` rows and geodata fields.

## Risks / open questions

- **No CSRF protection**: Any same-site page can POST forms or, in browsers that send cookies on cross-site requests under relaxed policies, risk increases. JSON POST endpoints likewise trust the session cookie only.
- **`socketio` CORS `*`** in `extensions.py`: broad origin allowance on the Socket.IO layer; mitigated only by how the app is hosted and authenticated connect logic.
- **Split realtime story**: Server emits `dm_message` / `group_message`, but the shipped client relies on **polling** in thread templates; latency and duplicate network patterns should be intentional or consolidated.
- **Subpath deployment**: `appUrl()` covers script root; ensure reverse proxy sets `SCRIPT_NAME` / prefix consistently with `request.script_root`.
- **Gym feed JSON `photo_url`**: Returned raw from the model; may be absolute URL or relative path; `app.js` renders in HTML without the server’s `media_url` filter — verify XSS and URL validity if content is ever user-controlled in unexpected ways.
- **School search offline**: `/api/schools` returns `total_loaded === 0` when IPEDS JSON is missing; UX points operators to `scripts/build_us_institutions.py`.

---

*Integration lane — multitask audit. File generated to support cross-lane consistency review.*
