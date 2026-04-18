# HackMESA-2026
GymLink

## Deploy on [Railway](https://railway.app)

1. Create a new project and deploy from this Git repo.
2. Open the **GymLink** service settings and set **Root Directory** to `gymlink` (so Nixpacks finds `requirements.txt`, `Procfile`, and `app.py`).
3. Under **Variables**, add:
   - **`SECRET_KEY`** — long random string (required for production cookies and sessions).
   - Optional **`DATABASE_URL`** — add the [Railway Postgres](https://docs.railway.app/databases/postgresql) plugin and attach its URL so data survives redeploys. If unset, the app uses **SQLite** under the Flask instance folder (ephemeral on Railway unless you mount a [volume](https://docs.railway.app/reference/volumes) on that path).
4. Deploy. The **Procfile** runs **gunicorn** with a **single** `GeventWebSocketWorker` (required for Flask-SocketIO / leaderboard live updates). **`GYMLINK_ASYNC_MODE=gevent`** is set in the Procfile for Linux.
5. Open the generated **`.up.railway.app`** URL (or attach a custom domain).

Local development is unchanged: run `python app.py` from `gymlink/` (threading async mode by default).

**Note:** `gunicorn` does not run on native Windows (it requires `fcntl`). To smoke-test the production server locally, use **WSL**, **Docker**, or deploy to Railway/Linux.
