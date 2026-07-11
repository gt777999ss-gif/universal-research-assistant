from __future__ import annotations

import asyncio
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx


async def deliver_notifications(channels: List[str], payload: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    message = format_message(payload)
    for channel in dict.fromkeys(channels):
        try:
            if channel == "webhook": await webhook(os.getenv("WEBHOOK_URL", ""), payload)
            elif channel == "telegram": await telegram(payload)
            elif channel == "discord": await discord(payload)
            elif channel == "email": await email(message)
            else: warnings.append(f"Unsupported notification channel: {channel}.")
        except ValueError as exc:
            warnings.append(str(exc))
        except Exception:
            warnings.append(f"{channel} notification was not delivered; provider error was redacted.")
    return warnings


async def webhook(url: str, payload: Dict[str, Any]) -> None:
    validate_url(url, "WEBHOOK_URL")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json={"text": format_message(payload), "research": payload})
        response.raise_for_status()


async def telegram(payload: Dict[str, Any]) -> None:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id: raise ValueError("Telegram notification not configured: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": format_message(payload)})
        response.raise_for_status()


async def discord(payload: Dict[str, Any]) -> None:
    url = os.getenv("DISCORD_WEBHOOK_URL", "")
    validate_url(url, "DISCORD_WEBHOOK_URL")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json={"content": format_message(payload)})
        response.raise_for_status()


async def email(message: str) -> None:
    required = {name: os.getenv(name, "") for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO")}
    if not all(required.values()): raise ValueError("Email notification not configured: SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM, and SMTP_TO are required.")
    await asyncio.to_thread(send_email, required, message)


def send_email(settings: Dict[str, str], message: str) -> None:
    email_message = EmailMessage()
    email_message["Subject"] = "Universal Research Assistant automation"
    email_message["From"] = settings["SMTP_FROM"]
    email_message["To"] = settings["SMTP_TO"]
    email_message.set_content(message)
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(settings["SMTP_HOST"], port, timeout=10) as client:
        if os.getenv("SMTP_USE_TLS", "true").lower() != "false": client.starttls()
        client.login(settings["SMTP_USERNAME"], settings["SMTP_PASSWORD"])
        client.send_message(email_message)


def validate_url(url: str, name: str) -> None:
    parsed = urlparse(url)
    if not url: raise ValueError(f"{name} is not configured; delivery was not attempted.")
    if parsed.scheme != "https" or not parsed.netloc: raise ValueError(f"{name} must be a valid HTTPS URL.")


def format_message(payload: Dict[str, Any]) -> str:
    links = ", ".join(item.get("download_url", "") for item in payload.get("downloads", []) if item.get("download_url"))
    return f"{payload['job_name']}: {payload['run_status']} | workflow {payload['workflow_id']} | results {payload['result_count']} | warnings {payload['warning_count']} | alerts {payload['alert_count']}\n{payload.get('summary', '')}\nReports: {links}\nDashboard: {payload['dashboard_url']}"
