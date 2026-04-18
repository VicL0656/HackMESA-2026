from __future__ import annotations

import uuid
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def file_was_chosen(file: FileStorage | None) -> bool:
    """True if the browser sent a filename (user picked a file), even if save failed."""
    return bool(file and getattr(file, "filename", None) and str(file.filename).strip())


def save_uploaded_image(
    file: FileStorage | None,
    prefix: str,
    *,
    max_bytes: int | None = None,
) -> str | None:
    if not file or not file.filename:
        return None
    limit = max_bytes
    if limit is None:
        limit = int(current_app.config.get("MAX_UPLOAD_IMAGE_BYTES", 25 * 1024 * 1024))
    name = secure_filename(file.filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return None
    upload_dir: Path = current_app.config["UPLOAD_FOLDER"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    fn = f"{prefix}_{uuid.uuid4().hex[:16]}{ext}"
    dest = upload_dir / fn
    file.stream.seek(0)
    data = file.read()
    if len(data) > limit:
        return None
    dest.write_bytes(data)
    return f"/uploads/{fn}"
