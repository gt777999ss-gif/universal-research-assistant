from __future__ import annotations

from typing import Any, Dict


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
        return {
            "channel": channel,
            "target": target,
            "sent": False,
            "status": "placeholder",
            "detail": "Webhook delivery framework is present; outbound delivery is intentionally not configured.",
        }
    return {
        "channel": channel,
        "target": target,
        "sent": False,
        "status": "placeholder",
        "detail": f"{channel} notification framework is present; provider credentials are not configured.",
    }
