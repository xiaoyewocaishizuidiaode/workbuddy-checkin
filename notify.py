#!/usr/bin/env python3
"""签到失败时发邮件。成功默认不发。"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def _enabled() -> bool:
    flag = os.environ.get("NOTIFY_ON_FAILURE", "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def send_failure_mail(subject: str, body: str) -> None:
    """仅失败调用。未配置 SMTP 则静默跳过（仍可依赖 GitHub Actions 失败邮件）。"""
    if not _enabled():
        return
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    mail_to = os.environ.get("NOTIFY_EMAIL_TO", "").strip() or user
    mail_from = os.environ.get("SMTP_FROM", "").strip() or user
    if not host or not user or not password or not mail_to:
        return

    port = int(os.environ.get("SMTP_PORT", "465") or "465")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body)

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, password)
            smtp.send_message(msg)
