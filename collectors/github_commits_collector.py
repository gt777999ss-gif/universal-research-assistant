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
KEYWORDS = {"video", "temporal", "motion", "frame", "diffusion", "transformer", "vae", "latent", "inference", "scheduler", "pipeline", "conditioning", "camera", "animation", "lora", "quantization", "cuda", "performance", "memory", "workflow", "node", "sampler", "checkpoint", "model", "comfyui", "cogvideo", "wan", "ltx"}
NOISE = {"typo", "format", "formatting", "lint", "lockfile", "version bump", "bump version", "merge branch", "ci", "translation"}
LAST_DIAGNOSTIC: Dict[str, Any] = {"status": "never_run"}


class GitHubCommitsError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"GitHub Commits {category}: {message}")
        self.category = category


async def collect_github_commits(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    results, _ = await collect_github_commits_with_diagnostics(query, days, limit)
    return results


async def collect_github_commits_with_diagnostics(query: str, days: int, limit: int, repositories: List[str] | None = None) -> Tuple[List[SearchResult], List[Dict[str, Any]]]:
    global LAST_DIAGNOSTIC
    if not enabled():
        return [], [{"status": "disabled", "reason": "GITHUB_COMMITS_ENABLED is false."}]
    days = int(os.getenv("GITHUB_COMMITS_LOOKBACK_DAYS", str(days)))
    diagnostics: List[Dict[str, Any]] = []
    candidates: List[SearchResult] = []
    detail_budget = max_detail_calls()
    for repo in repositories or watched_repositories():
        try:
            summaries, rate = await fetch_commits(repo, days, max_per_repo(), page=1)
            relevant, skipped = normalize_commits(repo, summaries, query, days)
            diagnostics.append({"repo": repo, "status": "ok" if relevant else "empty", "summaries_fetched": len(summaries), "relevant_count": len(relevant), "skipped": skipped, "rate_limit_remaining": rate.get("remaining", "")})
            candidates.extend(relevant)
        except GitHubCommitsError as exc:
            diagnostics.append({"repo": repo, "status": "failed", "reason": str(exc), "summaries_fetched": 0, "relevant_count": 0})
    candidates.sort(key=lambda item: commit_rank(item), reverse=True)
    detailed: List[SearchResult] = []
    for item in candidates:
        if detail_budget <= 0:
            detailed.append(item)
            continue
        try:
            detail, rate = await fetch_commit_detail(item.repo, item.commit_sha)
            detailed.append(apply_detail(item, detail))
            detail_budget -= 1
            if rate.get("remaining") is not None and int(rate["remaining"]) <= 2:
                diagnostics.append({"status": "rate_limit_guard", "reason": "Stopped optional detail calls because GitHub quota is low."})
                detail_budget = 0
        except GitHubCommitsError as exc:
            diagnostics.append({"repo": item.repo, "status": "detail_failed", "reason": str(exc)})
            detailed.append(item)
    LAST_DIAGNOSTIC = {"status": "completed", "authentication_mode": auth_mode(), "repositories_checked": len(repositories or watched_repositories()), "relevant_commit_count": len(detailed), "grouped_event_count": len(group_commit_results(detailed)), "details_fetched": max_detail_calls() - detail_budget}
    return detailed[:limit], diagnostics


async def fetch_commits(repo: str, days: int, per_page: int, page: int = 1) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return await github_get(repo, "commits", {"since": since, "per_page": min(max(1, per_page), 100), "page": max(1, page)})


async def fetch_commit_detail(repo: str, sha: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload, rate = await github_get(repo, f"commits/{sha}", {})
    if not isinstance(payload, dict):
        raise GitHubCommitsError("malformed JSON", "commit detail was not an object.")
    return payload, rate


async def github_get(repo: str, path: str, params: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    headers = {"User-Agent": os.getenv("RESEARCH_ASSISTANT_USER_AGENT", "universal-research-assistant/1.0"), "Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN", "").strip():
        headers["Authorization"] = f"Bearer {os.getenv('GITHUB_TOKEN', '').strip()}"
    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(15, connect=5, read=10, write=10), follow_redirects=True) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.get(f"{API_ROOT}/{repo}/{path}", params=params)
                if (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(min(float(response.headers.get("Retry-After", "1")), 5))
                    continue
                response.raise_for_status()
                return response.json(), rate_headers(response)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                category = "rate limit" if status == 429 or (status == 403 and exc.response.headers.get("X-RateLimit-Remaining") == "0") else "invalid token" if status == 401 else "repository missing" if status == 404 else "invalid parameters" if status == 422 else f"HTTP {status}"
                raise GitHubCommitsError(category, "GitHub request was rejected.") from exc
            except httpx.TimeoutException as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(1)
                    continue
                raise GitHubCommitsError("timeout", "GitHub request timed out.") from exc
            except ValueError as exc:
                raise GitHubCommitsError("malformed JSON", "GitHub response was not valid JSON.") from exc
            except httpx.HTTPError as exc:
                raise GitHubCommitsError("network error", "GitHub request failed.") from exc
    raise GitHubCommitsError("rate limit", "GitHub request remained rate limited after one retry.")


def normalize_commits(repo: str, commits: List[Dict[str, Any]], query: str, days: int) -> Tuple[List[SearchResult], List[Dict[str, str]]]:
    kept, skipped = [], []
    for item in commits:
        result = normalize_commit(repo, item)
        if not result:
            skipped.append({"reason": "malformed commit"}); continue
        if noise_reason(result):
            skipped.append({"sha": result.short_sha, "reason": noise_reason(result)}); continue
        if not relevant(result, query):
            skipped.append({"sha": result.short_sha, "reason": "not AI-video relevant"}); continue
        kept.append(result)
    return kept, skipped


def normalize_commit(repo: str, item: Dict[str, Any]) -> SearchResult | None:
    sha = str(item.get("sha") or "")
    commit = item.get("commit") or {}
    message = clean_html_text(str(commit.get("message") or "")).split("\n")[0]
    if not sha or not message: return None
    author = commit.get("author") or {}
    login = (item.get("author") or {}).get("login", "") if isinstance(item.get("author"), dict) else ""
    classification, importance, rationale = classify(message, repo)
    return SearchResult(source="github_commits", title=f"{repo}: {message}", url=str(item.get("html_url") or f"https://github.com/{repo}/commit/{sha}"), author=str(login or author.get("name") or repo), date=str(author.get("date") or commit.get("committer", {}).get("date") or "") or None, summary=message, full_text=message, image_url="", video_url="", repo=repo, commit_sha=sha, short_sha=sha[:12], commit_url=str(item.get("html_url") or ""), api_url=str(item.get("url") or ""), parent_count=len(item.get("parents") or []), verification_status=str((commit.get("verification") or {}).get("verified", "")), classification=classification, importance=importance, confidence="high" if classification != "other" else "low", rationale=rationale, source_type="github_commit", reason_selected=rationale, tags=["github_commits", repo, classification, importance])


def apply_detail(result: SearchResult, detail: Dict[str, Any]) -> SearchResult:
    files = detail.get("files") or []
    paths = [str(item.get("filename", "")) for item in files]
    result.changed_files = paths[:50]; result.additions = int(detail.get("stats", {}).get("additions", 0)); result.deletions = int(detail.get("stats", {}).get("deletions", 0)); result.parent_count = len(detail.get("parents") or []); result.verification_status = str((detail.get("commit", {}).get("verification") or {}).get("verified", result.verification_status)); result.full_text = f"{result.summary}\nChanged files: {', '.join(paths[:20])}"; return result


def relevant(result: SearchResult, query: str) -> bool:
    text = normalize_text(f"{result.repo} {result.summary} {result.full_text}")
    return bool(set(text.split()).intersection(KEYWORDS)) and ("video" in normalize_text(query) or any(token in text for token in KEYWORDS))


def noise_reason(result: SearchResult) -> str:
    text = normalize_text(result.summary)
    if any(term in text for term in NOISE) and not any(term in text for term in {"video", "model", "pipeline", "workflow"}): return "routine noise"
    if result.parent_count > 1 and len(text.split()) < 5: return "unhelpful merge commit"
    return ""


def classify(message: str, repo: str) -> Tuple[str, str, str]:
    text = normalize_text(message)
    if any(term in text for term in {"support", "model", "checkpoint"}): return "model_support", "high", "Adds or updates model support."
    if any(term in text for term in {"performance", "memory", "cuda", "quantization"}): return "performance", "high", "Targets runtime performance or resource use."
    if any(term in text for term in {"fix", "bug"}): return "bug_fix", "medium", "Fixes a relevant implementation issue."
    if any(term in text for term in {"workflow", "node", "sampler"}): return "workflow", "medium", "Changes an AI-video workflow component."
    if "doc" in text: return "documentation", "low", "Documents a potentially relevant capability."
    return "other", "low", "Matches tracked repository and AI-video relevance rules."


def commit_rank(item: SearchResult) -> Tuple[int, int, float]:
    return ({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(item.importance, 0), len(item.changed_files), datetime.fromisoformat(item.date.replace("Z", "+00:00")).timestamp() if item.date else 0)


def group_commit_results(items: List[SearchResult]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[SearchResult]] = {}
    for item in items: groups.setdefault((item.repo, item.classification), []).append(item)
    return [{"canonical_title": group[0].summary, "repository": repo, "date_range": [group[-1].date, group[0].date], "commit_members": [item.commit_url for item in group], "combined_changed_files": sorted({path for item in group for path in item.changed_files})[:50], "summary": group[0].rationale, "importance": group[0].importance, "confidence": group[0].confidence, "commit_count": len(group)} for (repo, _), group in groups.items()]


def watched_repositories() -> List[str]: return [str(repo) for repo in load_settings().get("sources", {}).get("github_commits", {}).get("repositories", [])]
def enabled() -> bool: return os.getenv("GITHUB_COMMITS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
def max_per_repo() -> int: return int(os.getenv("GITHUB_COMMITS_MAX_PER_REPO", str(load_settings().get("sources", {}).get("github_commits", {}).get("max_commits_per_repo", 30))))
def max_detail_calls() -> int: return int(os.getenv("GITHUB_COMMITS_MAX_DETAIL_CALLS", "15"))
def auth_mode() -> str: return "token" if os.getenv("GITHUB_TOKEN", "").strip() else "public"
def rate_headers(response: httpx.Response) -> Dict[str, Any]: return {"limit": response.headers.get("X-RateLimit-Limit"), "remaining": response.headers.get("X-RateLimit-Remaining"), "reset": response.headers.get("X-RateLimit-Reset")}
