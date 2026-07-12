from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


TEMPLATES: Dict[str, Dict[str, Any]] = {
    "ai_video_weekly": {
        "name": "AI Video Weekly",
        "description": "Weekly public-information briefing covering leading AI video platforms.",
        "topic": "AI video tools weekly developments",
        "queries": ["Google Veo", "Runway", "Kling AI", "Seedance", "Pika", "HeyGen", "Luma AI"],
        "sources": ["google_news", "youtube", "rss", "hacker_news", "github_releases"],
        "days": 7,
        "limit_per_source": 20,
        "output_formats": ["markdown", "html", "json"],
    },
    "ai_news_daily": {
        "name": "AI News Daily",
        "description": "Daily public-information briefing for recent AI developments.",
        "topic": "AI news daily developments",
        "queries": ["AI latest news", "AI product updates"],
        "sources": ["google_news", "reddit"],
        "days": 1,
        "limit_per_source": 20,
        "output_formats": ["markdown", "html", "json"],
    },
    "youtube_channel_watch": {
        "name": "YouTube Channel Watch",
        "description": "Public YouTube update watch using the official API when configured.",
        "topic": "YouTube channel updates",
        "queries": ["latest channel videos"],
        "sources": ["youtube"],
        "days": 7,
        "limit_per_source": 20,
        "output_formats": ["markdown", "json"],
    },
    "tiktok_pet_thailand": {
        "name": "TikTok Pet Thailand",
        "description": "Legal public-information research on Thailand pet discussions and content signals. No logged-in TikTok scraping.",
        "topic": "TikTok Shop Thailand pet products public discussions",
        "queries": [
            "TikTok Shop Thailand pet products",
            "Thailand pet backpack",
            "Thailand pet bed",
            "Thailand pet stroller",
            "Thailand pet water fountain",
            "Thailand pet feeder",
        ],
        "sources": ["google_news", "reddit", "youtube", "tiktok"],
        "days": 7,
        "limit_per_source": 20,
        "output_formats": ["markdown", "html", "json"],
    },
    "competitor_monitor": {
        "name": "Competitor Monitor",
        "description": "Public-information monitoring template for named organizations or products.",
        "topic": "competitor public developments",
        "queries": ["competitor news updates"],
        "sources": ["google_news", "reddit"],
        "days": 7,
        "limit_per_source": 20,
        "output_formats": ["markdown", "json"],
    },
    "custom": {
        "name": "Custom Research",
        "description": "Starting point for a user-defined public-information workflow.",
        "topic": "custom research topic",
        "queries": [],
        "sources": ["google_news"],
        "days": 30,
        "limit_per_source": 20,
        "output_formats": ["markdown", "html", "json"],
    },
}


def list_templates() -> List[Dict[str, Any]]:
    return [{"id": key, **deepcopy(value)} for key, value in TEMPLATES.items()]


def get_template(template_id: str) -> Dict[str, Any]:
    template = TEMPLATES.get(template_id)
    if not template:
        raise KeyError(template_id)
    return deepcopy(template)
