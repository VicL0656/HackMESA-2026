"""Optional SMTP email (password reset, etc.)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app


def mail_configured() -> bool:
    return bool((current_app.config.get("MAIL_SERVER") or "").strip())


def send_email(to_addr: str, subject: str, body_text: str) -> bool:
    if not mail_configured():
        return False
    server = (current_app.config.get("MAIL_SERVER") or "").strip()
    port = int(current_app.config.get("MAIL_PORT") or 587)
    use_tls = bool(current_app.config.get("MAIL_USE_TLS", True))
    user = (current_app.config.get("MAIL_USERNAME") or "").strip()
    password = (current_app.config.get("MAIL_PASSWORD") or "").strip()
    sender = (current_app.config.get("MAIL_DEFAULT_SENDER") or user or "noreply@localhost").strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.set_content(body_text)

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
    except OSError:
        return False
    return True
