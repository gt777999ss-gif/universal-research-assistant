from __future__ import annotations

import os
from typing import Any, Dict

import httpx


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
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(webhook_url, json={"message": message})
                response.raise_for_status()
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
