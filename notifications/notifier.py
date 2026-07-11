from __future__ import annotations

import os
from typing import Any, Dict

from notifications.providers import deliver_notifications


SUPPORTED_CHANNELS = {"email", "telegram", "discord", "webhook"}


async def send_test_notification(channel: str, target: str = "", message: str = "") -> Dict[str, Any]:
    if channel not in SUPPORTED_CHANNELS:
        return {
            "channel": channel,
            "sent": False,
            "status": "unsupported",
            "detail": f"Supported channels: {', '.join(sorted(SUPPORTED_CHANNELS))}.",
        }
    if channel == "webhook":
        webhook_url = os.getenv("WEBHOOK_URL", "")
        if webhook_url:
            warnings = await deliver_notifications(["webhook"], {"job_name": "Notification test", "run_status": "test", "workflow_id": "", "result_count": 0, "warning_count": 0, "alert_count": 0, "summary": message, "downloads": [], "dashboard_url": "/ui/automation"})
            if warnings:
                return {"channel": channel, "target": "configured_webhook", "sent": False, "status": "delivery_failed", "detail": warnings[0]}
            return {
                "channel": channel,
                "target": "configured_webhook",
                "sent": True,
                "status": "sent",
                "detail": "Webhook notification test was sent.",
            }
        return {
            "channel": channel,
            "target": target,
            "sent": False,
            "status": "not_configured",
            "detail": "WEBHOOK_URL is not configured; webhook delivery was not attempted.",
        }
    return {
        "channel": channel,
        "target": target,
        "sent": False,
        "status": "placeholder",
        "detail": f"{channel} notification framework is present; provider credentials are not configured.",
    }


async def send_automation_notifications(channels: list[str], payload: Dict[str, Any]) -> list[str]:
    """Deliver only to explicitly configured channels; provider errors stay redacted."""
    return await deliver_notifications(channels, payload)
