import os

from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

# Use GYMLINK_ASYNC_MODE=gevent with gunicorn + GeventWebSocketWorker on Railway/Linux.
_socketio_mode = (os.environ.get("GYMLINK_ASYNC_MODE") or "threading").strip().lower()
if _socketio_mode not in ("threading", "gevent", "eventlet"):
    _socketio_mode = "threading"

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
socketio = SocketIO(cors_allowed_origins="*", async_mode=_socketio_mode)

login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
