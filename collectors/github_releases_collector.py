from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import httpx

from collectors.common import load_settings
from models import SearchResult
from processors.filter import normalize_text
from processors.text_cleaning import clean_html_text


LOGGER = logging.getLogger(__name__)
API_ROOT = "https://api.github.com/repos"
MAX_ATTEMPTS = 2
VIDEO_REPOSITORIES = {
    "comfyanonymous/comfyui", "comfy-org/comfyui-manager", "lightricks/ltx-video",
    "thudm/cogvideo", "hunyuanvideo/hunyuanvideo", "open-sora/open-sora", "ailab-cvc/videocrafter",
}
AI_VIDEO_TERMS = {
    "comfyui", "ltx video", "cogvideo", "hunyuanvideo", "open sora", "videocrafter",
    "ai video", "video generation", "text to video", "image to video", "generative video",
    "video model", "video workflow",
}


class GitHubReleasesError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"GitHub Releases {category}: {message}")
        self.category = category


async def collect_github_releases(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    results, _ = await collect_github_releases_with_diagnostics(query, days, limit)
    return results


async def collect_github_releases_with_diagnostics(query: str, days: int, limit: int) -> Tuple[List[SearchResult], List[Dict[str, Any]]]:
    results: List[SearchResult] = []
    diagnostics: List[Dict[str, Any]] = []
    for repo in watched_repositories():
        try:
            releases = await fetch_releases(repo, per_page=min(max(1, limit), 100), page=1)
            normalized = [normalize_release(repo, item) for item in releases]
            kept = [item for item in normalized if item and is_current(item, days) and is_relevant(item, query)]
            results.extend(item for item in kept if item)
            diagnostics.append({"repo": repo, "status": "ok" if kept else "empty", "release_count": len(releases), "result_count": len(kept), "skipped": len(releases) - len(kept)})
        except GitHubReleasesError as exc:
            diagnostics.append({"repo": repo, "status": "failed", "release_count": 0, "result_count": 0, "reason": str(exc)})
            LOGGER.warning("GitHub Releases repo=%s error=%s", repo, exc)
    return sorted(results, key=lambda item: release_rank(item, query), reverse=True)[:limit], diagnostics


async def fetch_releases(repo: str, per_page: int, page: int = 1) -> List[Dict[str, Any]]:
    params = {"per_page": max(1, min(per_page, 100)), "page": max(1, page)}
    headers = {"User-Agent": github_user_agent(), "Accept": "application/vnd.github+json"}
    endpoint = f"{API_ROOT}/{repo}/releases"
    async with github_http_client(headers) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.get(endpoint, params=params)
                if (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < MAX_ATTEMPTS:
                    delay = retry_delay(response)
                    LOGGER.warning("GitHub Releases repo=%s status=%s retry_after=%s", repo, response.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise GitHubReleasesError("malformed JSON", "response did not contain a release list.")
                LOGGER.info("GitHub Releases repo=%s page=%s status=%s release_count=%s", repo, params["page"], response.status_code, len(payload))
                return payload
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                rate_limited = status == 429 or (status == 403 and exc.response.headers.get("X-RateLimit-Remaining") == "0")
                raise GitHubReleasesError("rate limit" if rate_limited else f"HTTP {status}", "release request was rejected.") from exc
            except httpx.TimeoutException as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(1)
                    continue
                raise GitHubReleasesError("timeout", "release request timed out.") from exc
            except GitHubReleasesError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(1)
                    continue
                raise GitHubReleasesError("network or response error", "release request failed.") from exc
    raise GitHubReleasesError("rate limit", "release request remained rate limited after one retry.")


def watched_repositories() -> List[str]:
    config = load_settings().get("sources", {}).get("github_releases", {})
    return [str(repo) for repo in config.get("repositories", []) if repo]


def normalize_release(repo: str, release: Dict[str, Any]) -> SearchResult | None:
    version = str(release.get("tag_name") or release.get("name") or "").strip()
    if not version:
        return None
    name = clean_html_text(str(release.get("name") or version))
    notes = clean_html_text(str(release.get("body") or ""))
    author = str((release.get("author") or {}).get("login") or "") if isinstance(release.get("author"), dict) else ""
    return SearchResult(
        source="github_releases",
        title=f"{repo} {name}",
        url=str(release.get("html_url") or f"https://github.com/{repo}/releases/tag/{version}"),
        author=author or repo,
        date=parse_date(release.get("published_at") or release.get("created_at")),
        summary=notes[:700] or f"Release {version} from {repo}.",
        full_text=notes,
        image_url="",
        video_url="",
        repo=repo,
        version=version,
        release_notes=notes,
        reason_selected=f"Release from watched GitHub repository {repo}.",
        tags=["github_releases", repo, version],
    )


def is_relevant(result: SearchResult, query: str) -> bool:
    text = normalize_text(f"{result.repo} {result.title} {result.release_notes}")
    normalized_query = normalize_text(query)
    if any(term in normalized_query for term in AI_VIDEO_TERMS):
        return result.repo.lower() in VIDEO_REPOSITORIES or any(term in text for term in AI_VIDEO_TERMS)
    return bool(set(normalized_query.split()).intersection(text.split()))


def is_current(result: SearchResult, days: int) -> bool:
    if not result.date:
        return True
    try:
        return datetime.fromisoformat(result.date.replace("Z", "+00:00")) >= datetime.now(timezone.utc) - timedelta(days=max(1, days))
    except ValueError:
        return True


def release_rank(result: SearchResult, query: str) -> Tuple[float, float]:
    query_terms = set(normalize_text(query).split())
    release_terms = set(normalize_text(f"{result.repo} {result.title} {result.release_notes}").split())
    watched_bonus = 1.0 if result.repo.lower() in VIDEO_REPOSITORIES else 0.25
    return (len(query_terms.intersection(release_terms)) + watched_bonus, timestamp(result.date))


def parse_date(value: Any) -> str | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def timestamp(value: str | None) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def github_user_agent() -> str:
    return os.getenv("RESEARCH_ASSISTANT_USER_AGENT", "").strip() or "universal-research-assistant/1.0 (+public-github-releases-research)"


def github_http_client(headers: Dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout=15.0, connect=5.0, read=10.0, write=10.0), follow_redirects=True)


def retry_delay(response: httpx.Response) -> float:
    try:
        return max(0.0, min(float(response.headers.get("Retry-After", "1")), 10.0))
    except ValueError:
        return 1.0
