# Database lane — GymLink multitask audit

## Scope

This lane reviewed persistence for GymLink: SQLAlchemy/Flask-SQLAlchemy models in `models.py`, demo/setup in `seed.py`, absence of Alembic (or equivalent) migration packages, SQLite default path (`instance/gymlink.db`), startup schema behavior in `app.py`, declared indexes/constraints versus what SQLite receives, and how the ORM maps to tables. No application code was changed; this document is discovery-only.

## Work summary

- **Models (`models.py`)**: Twenty-two mapped tables covering users/auth, gyms and check-ins, swipes/friend requests/matches/DM messages, workouts (including JSON `line_items`), weight logs, goals, outdoor activities, PRs and streaks, notifications, password reset tokens, friend groups/group messages/group challenges, favorites, daily challenges and completions.
- **Seed (`seed.py`)**: `db.drop_all()` then `db.create_all()` inside app context; bulk inserts for demo users (`jordan_blake` presenter pattern), streaks, PRs, matches, sample messages/workouts/outdoors/weight logs/daily challenge rows; integrates `tom_friend` and asserts presenter match counts; invokes `workout_helpers.recompute_streak_for_user` after inserts.
- **Migrations**: No Alembic (or Flask-Migrate) directory or revision chain in-repo. Schema evolution on SQLite relies on **`db.create_all()`** plus **ad hoc `ALTER TABLE`** helpers in `app.py` (`_sqlite_add_missing_columns`, `_migrate_sqlite_username_column`) that run only when `db.engine.dialect.name == "sqlite"`.
- **`instance/gymlink.db`**: Used when neither `DATABASE_URL` nor `SQLALCHEMY_DATABASE_URI` is set; URI is `sqlite:///{instance_path}/gymlink.db` with `instance_path = Flask.instance_path` (typically `instance/` next to `app.py`). Production can point at Postgres via env.
- **Indexes**: Mostly `index=True` on FK and lookup columns; one explicit composite index `ix_check_ins_user_active` on `(user_id, checked_out_at)`. Uniqueness is enforced via `unique=True`, `UniqueConstraint`, and SQLite check constraints declared in SQLAlchemy.
- **ORM vs tables**: Single source of truth is declarative models; Flask-SQLAlchemy creates tables from metadata. Older SQLite files may diverge briefly until `ALTER` paths add columns; `line_items` is added via `TEXT` DDL in `_sqlite_add_missing_columns` while the model uses `db.JSON` — consistent with SQLite JSON-as-text handling.

## Contracts & interfaces

| Concern | Contract |
| --- | --- |
| **Database URI** | `DATABASE_URL` or `SQLALCHEMY_DATABASE_URI` (postgres URL normalized from legacy `postgres://`); fallback SQLite file path as above (`app.py`). |
| **Table names** | Python class names map to lowercase snake `_tablename_` values: e.g. `User` → `users`, `FriendGroupMember` → `friend_group_members`, `DailyChallengeComplete` → `daily_challenge_completes`. |
| **Identity / auth persistence** | `users` carries `username`, `email` (both unique indexed), `password_hash`, profile/school/privacy fields; `login_manager.user_loader` uses `db.session.get(User, id)`. `password_reset_tokens` stores hashed token + expiry. |
| **Social graph & messaging** | `swipes` (pair uniqueness, direction/right-left checks), `friend_requests`, `matches` (`user_a_id < user_b_id` check), `messages` per match. Group chat: `friend_groups`, `friend_group_members`, `group_messages`, `group_challenge_completes`. |
| **Gym locality** | `gyms` (optional unique `osm_key`), `check_ins` tying `users` ↔ `gyms` with timestamps; composite index supports “active” queries by user + checkout state. |
| **Fitness data** | `workouts`, `weight_logs` (visibility check), `outdoor_activities` (kind check), `personal_records` (unique per user+exercise), `goals`, `streaks` (`user_id` unique). |
| **Engagement** | `notifications` (kind check, optional `dedupe_key` unique per user), `daily_challenges` / `daily_challenge_completes`, `friend_favorites`. |
| **Deletion semantics** | `user_delete.delete_user_account` manually deletes dependents in FK-safe order (not DB-level cascading); aligns with SQLite’s typical lack of automatic cascade unless configured server-side elsewhere. |

## Dependencies on other lanes

- **Backend**: Routes and helpers (`routes/*`, `workout_helpers`, `notification_helpers`, `tom_friend`, `gym_store`, etc.) own transaction boundaries and queries; DB lane assumes they honor model constraints (e.g. ordered match IDs, swipe direction enum).
- **Integration**: Any API or form DTO must stay aligned with column names and types on `User`, `Workout`, `Match`, etc., especially JSON fields (`workout_split` string, `line_items` JSON), boolean-as-integer SQLite behavior for older columns, and date vs datetime columns.
- **Frontend**: Displays depend on seeded/demo shape from `seed.py` and presenter account contract; inbox unread uses `notifications.read_at`.

## Risks / open questions

- **No versioned migrations**: Postgres or long-lived SQLite beyond `create_all`/ALTER hacks has no repeatable upgrade path in-repo; risk of env drift between developers and production.
- **SQLite-only ALTER path**: `_sqlite_add_missing_columns` never runs on Postgres; deploying new columns to Postgres requires manual DDL or separate tooling — model-only changes might not apply automatically.
- **Schema vs model drift on legacy DB**: If a column is renamed in Python but not added to the ALTER whitelist, SQLite files could silently miss indexes/constraints declared only on fresh `create_all` builds until someone resets DB.
- **Seed destructive by design**: `drop_all()` wipes all data; documenting “never run seed against production” is important for ops.
- **JSON storage**: Mixed use of string JSON (`workout_split` migrated as TEXT) and `Workout.line_items` (TEXT DDL + `db.JSON`) should be exercised in integration tests for encoding edge cases across SQLite and Postgres.
