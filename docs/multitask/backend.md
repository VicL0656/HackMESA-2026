# Backend — GymLink multitask audit

## Scope

Flask application factory in `app.py`: configuration (database URI, session/cookies on Railway, Overpass/gym radius, upload limits, mail settings), `db.create_all()` plus SQLite-only column migrations, blueprint registration, root/API routes, static upload serving, one global `404` handler, and Socket.IO `connect` (room `user_<id>`). Extensions live in `extensions.py` (SQLAlchemy, LoginManager, Bcrypt, SocketIO with `GYMLINK_ASYNC_MODE`). HTTP routes are split across `routes/*.py`; there is **no** `services/` package—logic sits in routes plus helpers (`*_util.py`, `*_helpers.py`, `gym_store.py`, `osm_gyms.py`, etc.). Auth is session + `flask_login` with `user_loader` on `models.User`. Email is optional SMTP via `mail_util.py`. File uploads use `uploads_util.py` and `app.config["UPLOAD_FOLDER"]` under the instance path.

## Work summary

| Blueprint | `url_prefix` | Role |
|-----------|--------------|------|
| `auth` | — | Register, login, logout, forgot/reset password |
| `account` | `/account` | Settings form, home-gym JSON APIs, account delete |
| `workouts` | `/workouts` | Log/edit/delete gym workouts; images |
| `leaderboard` | — | Home dashboard at `/leaderboard` |
| `social` | — | Friends, DMs, groups, public profile, feed, profile POSTs |
| `inbox` | `/inbox` | Notification inbox + mark read |
| `gym` | `/gym` | JSON check-in/out + co-present feed |
| `outdoor` | `/outdoor` | Outdoor activity log + per-kind history |
| `weights` | `/weights` | Body-weight log + delete entry |

**App-level routes:** `GET /`, `GET /log` (redirect), `GET /health`, `GET /uploads/<path:name>`, `GET /api/schools` (JSON), `GET /api/me/workout-today` (JSON, login required). **Realtime:** `realtime.py` emits `leaderboard_update`, `dm_message`, `group_message` to Socket.IO rooms; `app.py` joins clients to `user_<user_id>` on connect.

**Error handling:** Global `404` → `404.html`. Other failures use `flash` + redirect, `jsonify(..., 4xx)`, or `abort(403|404)` in routes—no generic `500` handler.

## Contracts & interfaces

**Blueprints / endpoints (concrete paths)**

- **auth:** `GET/POST /register`, `GET/POST /login`, `GET /logout`, `GET/POST /forgot-password`, `GET/POST /reset-password/<token>`
- **account:** `GET/POST /account/settings`; `POST /account/api/city-search`, `/account/api/gym-search`, `/account/api/gym-pick`, `/account/api/gym-manual` (JSON in/out); `POST /account/delete-account`
- **workouts:** `GET/POST /workouts/log`, `GET/POST /workouts/<int:workout_id>/edit`, `POST /workouts/<int:workout_id>/delete`
- **leaderboard:** `GET /leaderboard` (`leaderboard.home`)
- **inbox:** `GET /inbox`, `POST /inbox/read/<int:notif_id>`, `POST /inbox/read-all`
- **gym:** `POST /gym/checkin`, `POST /gym/checkout`, `GET /gym/feed` (JSON)
- **outdoor:** `GET/POST /outdoor/log`, `GET /outdoor/exercise/<kind>`
- **weights:** `GET/POST /weights/log`, `POST /weights/log/<int:log_id>/delete`
- **social:** `POST /friends/add`; `GET /friends/username-suggest`; `POST /friends/favorite/<int:other_id>`, `/friends/remove/<int:other_id>`; `POST /friends/requests/<int:request_id>/accept|decline`; `GET /feed`; `GET /matches/<int:match_id>/poll`; `GET/POST /matches/<int:match_id>`; `GET/POST /groups`, `/groups/new`; `GET /groups/<int:group_id>/poll`; `GET/POST /groups/<int:group_id>`; `POST /groups/<int:group_id>/leave`; `GET/POST /add-friend`, `/connect/<username>`; `POST /profile/school`, `/profile/update`, `/profile/body-weight`, `/profile/photo`; `POST /profile/goals/add`, `/profile/goals/<int:goal_id>/toggle|delete|update`; `GET /profile`

**Auth contract:** `@login_required` on protected routes; `login_view` = `auth.login`. Identification uses email or `@username` via `username_utils.resolve_user_by_email_or_username`. Password hashing: `bcrypt` (`extensions.bcrypt`).

**Mail:** Env-driven `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`. If `MAIL_SERVER` is empty, `mail_util.send_email` is a no-op and forgot-password flashes a dev-visible link.

**Uploads:** `save_uploaded_image` → stores under instance `uploads/` and returns `/uploads/<filename>`; allowed extensions `{.jpg,.jpeg,.png,.webp,.gif}`; size capped by `MAX_UPLOAD_IMAGE_BYTES` / `MAX_PROFILE_PHOTO_BYTES` / `MAX_CONTENT_LENGTH`. Served only through `GET /uploads/<name>` (basename only; path sanitized).

**External HTTP:** Overpass (`OVERPASS_API_URL`), geocoding/city search modules as used by gym flows; configurable `GYMLINK_HTTP_USER_AGENT`.

**Socket.IO:** Clients must authenticate (session/`_user_id`); otherwise `disconnect()`.

## Dependencies on other lanes

- **Frontend / templates:** Most routes render Jinja templates and expect flash/session UX; gym and account JSON endpoints and poll URLs assume specific client payloads and polling behavior aligned with JS.
- **Database / models:** All persistence goes through SQLAlchemy models in `models.py` and migrations implied by `_sqlite_add_missing_columns` / `_migrate_sqlite_username_column`—Postgres deployments rely on tables existing; SQLite-only ALTER paths do not apply.
- **Assets / static:** `school_search` reads bundled institution data; `media_url` template filter resolves upload paths for feeds and profiles.

## Risks / open questions

- **Secrets:** Default `SECRET_KEY` when unset is suitable only for development; resets and sessions depend on it.
- **Operational email:** Forgot-password exposes the reset link in the flash when SMTP is not configured—insecure on any shared host.
- **Socket.IO:** `cors_allowed_origins="*"` and room-based messaging require trust in session binding; no per-event auth beyond connect.
- **Error surface:** No centralized `500` handler or logging hook; API consumers may get generic Werkzeug HTML on unhandled exceptions.
- **SQLite startup migrations:** One-off `ALTER TABLE` logic is SQLite-specific; schema drift on Postgres must be managed elsewhere.
- **Uploads:** No virus scanning; large limits (25 MB) increase abuse and disk use on the instance volume.
