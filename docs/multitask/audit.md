# GymLink multitask — auditor report

## Inputs read

All four lane reports were read: `docs/multitask/frontend.md`, `docs/multitask/backend.md`, `docs/multitask/integration.md`, `docs/multitask/database.md`.

## Cross-check (consistency)

| Area | Assessment |
| --- | --- |
| **HTTP ↔ UI** | `integration.md` screen→route table matches `backend.md` blueprint paths. `frontend.md` hooks (`#gym-feed-page`, school/friend autocomplete, leaderboard socket) align with endpoints listed in `integration.md` (`/gym/feed`, `/gym/checkin`, `/gym/checkout`, `/api/schools`, `/friends/username-suggest`, `/api/me/workout-today`, `/account/api/*`). |
| **Env vars** | `integration.md` env table is consistent with `backend.md` (mail, Railway cookies, Overpass, `DATABASE_URL` / `SQLALCHEMY_DATABASE_URI`, `GYMLINK_*`). `database.md` URI contract matches `backend.md` / `app.py` description. |
| **DB ↔ API** | `database.md` tables (`users`, `check_ins`, `gyms`, `matches`, `messages`, `workouts`, `notifications`, etc.) support the flows all lanes describe (check-in JSON, feed, DMs/groups, workouts, inbox). No lane contradicts column ownership. |
| **Auth end-to-end** | Session + `Flask-Login` + `@login_required` on JSON routes is consistent across `backend.md` and `integration.md`. `frontend.md` assumes `current_user` and flash categories — matches server-rendered pattern. |
| **Realtime** | All lanes agree: `leaderboard_update` is consumed in `app.js`; `dm_message` / `group_message` are emitted server-side but threads use HTTP polling — intentional or tech debt is an **alignment** question, not a doc conflict. |

## Issues by severity

### blocking

- **Secrets in production:** `backend.md` notes a dev-suitable default `SECRET_KEY` when unset — unsafe for any shared or production deployment (sessions, reset tokens).
- **Password reset UX when mail is off:** Reset link surfaced in flash without SMTP — unacceptable on multi-user or internet-facing hosts (`backend.md`).
- **Postgres schema changes:** `database.md` + `backend.md` — no Alembic/Flask-Migrate; SQLite-only `ALTER` helpers do not run on Postgres. Shipping new columns to Postgres without a repeatable migration path is an operational blocker for safe releases.

### should-fix

- **No CSRF tokens:** `integration.md` — mutations rely on same-origin session only; JSON POST endpoints share that posture.
- **Socket.IO CORS:** `integration.md` / `backend.md` — broad `cors_allowed_origins` combined with session-bound connect needs explicit threat model and tightening for production.
- **Error surface:** `backend.md` — no centralized 500 handler/logging; APIs may return Werkzeug HTML on exceptions.
- **XSS / HTML safety:** `frontend.md` flags `innerHTML` paths and possible unescaped gym-name interpolation in `account_settings.html`; `integration.md` notes `photo_url` in gym feed JSON rendered without `media_url` filter in `app.js` — worth verifying for user-controlled content.
- **Upload abuse:** `backend.md` — large limits, no scanning; instance disk exposure.

### nice-to-have

- **a11y:** `frontend.md` — bottom nav emoji-only labels, empty `alts`, autocomplete keyboard patterns.
- **CDN / CSP:** `frontend.md` — Tailwind, Socket.IO, Chart.js from CDNs; production CSP story open.
- **Client duplication:** `frontend.md` — share logic split between `app.js` and inline templates.
- **Operational docs:** `database.md` — explicit “never `seed.py` against production” runbook.

## Verdict

**needs alignment** — The four lanes describe a coherent Flask + Jinja + `static/app.js` system with matching routes and models. Before treating the app as production-hardened, align on **secrets/mail behavior**, **CSRF and Socket.IO CORS policy**, and **a real migration strategy for non-SQLite**; address **reset-link exposure** and **HTML safety** on settings/feed JSON as prioritized fixes.

## Gaps in writeups alone

Auditor did not re-open source files; if any route name, JSON key, or template hook drifted after these reports were written, re-verify in `app.py`, `routes/*.py`, `static/app.js`, and the referenced templates.
