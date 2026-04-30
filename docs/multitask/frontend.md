# GymLink — Frontend lane

## Scope

Jinja templates under `templates/` (including partials `_friend_home_row.html`, `_exercise_datalist.html`), global bundle `static/app.js`, Tailwind CDN + Socket.IO loaded from `templates/base.html`, and page-local `<script>` / `<style>` in several templates (`feed.html`, `log_workout.html`, `match_thread.html`, `group_thread.html`, `account_settings.html`, `weight_log.html`, `outdoor_exercise.html`, `profile.html`). No SPA; server-rendered HTML with progressive enhancement.

## Work summary

- **Base layout (`base.html`):** Defines blocks `title`, `head`, `content`; exposes `window.GYMLINK_SCRIPT_ROOT` from `request.script_root`; flashes via `get_flashed_messages`; bottom nav when authenticated linking `leaderboard.home`, `inbox.inbox_home`, `workouts.log_workout`, `social.feed`, `social.profile`; body `data-workout-days`, `data-reminder-hour/minute` for reminders.
- **`static/app.js` (DOMContentLoaded):** Leaderboard tabs + Socket.IO reload on `leaderboard_update` (`leaderboard.html`); gym live feed polling + geo check-in/out (`feed.html` meta `#gym-feed-page`); PR toast fade (`log_workout.html` `#pr-toast`); school autocomplete (`register.html`, `profile.html` via `data-school-autocomplete`); friend username autocomplete (`add_friend.html`); delegated `.gymlink-share-pr`; daily workout reminders + `#gymlink-enable-notifications` in settings.
- **Inline scripts:** Feed/challenge/general share buttons (`.gymlink-feed-share` in `feed.html`, `leaderboard.html`) use Web Share API or clipboard/`prompt`; `log_workout.html` toggles readonly/add-row UX for split vs off-plan; `match_thread.html` polls/sends DM XHR; `group_thread.html` toggles gear `aria-expanded`; `account_settings.html` gym search (POST geocode/query + pick/manual); Chart.js charts in `weight_log.html`, `outdoor_exercise.html`, `profile.html`; large split-editor logic in `profile.html`.
- **Client-side validation:** Mostly HTML5 — `required`, `minlength`/`maxlength`, `pattern` on username (`register.html`, `account_settings.html`), `type="email"`, `min`/`max`/`step` on numbers, `inputmode`; `confirm()` on destructive forms (`feed.html`, `weight_log.html`). No unified JS validator; template-added rows (`log-workout-form`) may omit `required` until submit (browser validates visible required fields).

## Contracts & interfaces

- **`window.GYMLINK_SCRIPT_ROOT`:** Prefix for `appUrl()` GET/POST paths (mounted apps / script root).
- **REST-ish JSON:** `GET` `gym.gym_feed_json` (`data-feed-url`); `POST` `gym.checkin` / `gym.checkout` with `{ latitude, longitude }` / `{}`; responses expect `{ ok, ... }` and optional `nearest_gym`, `nearest_miles`/`nearest_meters`, `hint`. `GET` `/api/schools?q=&limit=` → `{ results, total_loaded }`. `GET` `social.friends_username_suggest` → `{ ok, users: [{ username, name, photo_url }] }`. `GET` `/api/me/workout-today` → `{ logged: bool }`.
- **Socket.IO:** Client listens for `leaderboard_update`; server must emit that event for live leaderboard refresh.
- **DOM hooks:** `#leaderboard-root` + `data-active-tab`; `#gym-feed-page` dataset URLs; `[data-school-autocomplete]`, `[data-friend-username-autocomplete]` + `data-suggest-url`; `.gymlink-share-pr` `data-weight` / `data-exercise`; `#dm-chat-root` + `data-poll-url` in `match_thread.html`.

## Dependencies on other lanes

- **Backend / routes:** All `url_for` targets must remain stable (`auth.*`, `account.settings`, `gym.*`, `social.*`, `workouts.*`, `leaderboard.home`, `weights.*`, `outdoor.*`, `inbox.*`). Flash categories `error`, `success`, `info` drive banner styling.
- **Data & media:** Templates assume `current_user`, `media_url` / `school_badge` filters, preset exercise names for `_exercise_datalist.html`, and inbox unread injection in base context.
- **Integration:** Geolocation/OpenStreetMap copy in `feed.html` matches actual check-in behaviour; school seed message in `app.js` references `scripts/build_us_institutions.py`.

## Risks / open questions

- **a11y:** Bottom nav uses emoji-only labels without `aria-label`; many images use empty `alt`. Custom autocompletes use `role="listbox"`/`option` but lack arrow-key roving tabindex; leaderboard tab buttons are not `role="tablist"` / `aria-selected`.
- **CDN / CSP:** Tailwind, Socket.IO, Chart.js loaded from CDNs — production CSP and offline behaviour undefined.
- **Security / UX:** `innerHTML` in `app.js` for user lists escapes via separate paths but gym search in `account_settings.html` interpolates gym names without escaping; delegated share handlers rely on sanitized `data-text` from server templates.
- **Duplication:** Share logic split between `app.js` (PR) and inline `feed.html` / `leaderboard.html` (feed/challenge).
