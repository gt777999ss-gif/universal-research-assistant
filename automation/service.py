from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from automation.store import get_job, has_execution_key, list_jobs, list_runs, save_change, save_job, save_run, utc_now


WorkflowRunner = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
WorkflowLoader = Callable[[str], Optional[Dict[str, Any]]]
AlertSaver = Callable[[Dict[str, Any]], str]
Notifier = Callable[[List[str], Dict[str, Any]], Awaitable[List[str]]]


PRESETS = {
    "ai_video_daily": {"name": "AI Video Daily", "template": "ai_video_weekly", "overrides": {"days": 1}, "schedule_type": "daily", "hour": 8, "minute": 0},
    "ai_video_weekly": {"name": "AI Video Weekly", "template": "ai_video_weekly", "overrides": {"days": 7}, "schedule_type": "weekly", "weekday": 0, "hour": 8, "minute": 0},
    "ai_news_daily": {"name": "AI News Daily", "template": "ai_news_daily", "overrides": {"days": 1}, "schedule_type": "daily", "hour": 8, "minute": 30},
    "tiktok_pet_thailand_daily": {"name": "TikTok Pet Thailand Daily", "template": "tiktok_pet_thailand", "overrides": {"days": 1}, "schedule_type": "daily", "hour": 9, "minute": 0},
    "youtube_channel_watch_daily": {"name": "YouTube Channel Watch Daily", "template": "youtube_channel_watch", "overrides": {"days": 1}, "schedule_type": "daily", "hour": 9, "minute": 30},
    "competitor_monitor_daily": {"name": "Competitor Monitor Daily", "template": "competitor_monitor", "overrides": {"days": 1}, "schedule_type": "daily", "hour": 10, "minute": 0},
}


class AutomationScheduler:
    """Best-effort in-process scheduler; external /automation/tick is the reliable mode."""
    def __init__(self, tick: Callable[[], Awaitable[List[Dict[str, Any]]]], interval_seconds: int = 3600) -> None:
        self.tick = tick
        self.interval_seconds = interval_seconds
        self.running = False
        self.last_warnings: List[str] = []

    async def loop_forever(self) -> None:
        self.running = True
        while self.running:
            try:
                await self.tick()
            except Exception as exc:
                self.last_warnings.append(f"Automation scheduler error: {exc}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self.running = False


def create_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now()
    job = {"id": str(uuid4()), "name": payload["name"], "enabled": bool(payload.get("enabled", False)), "template": payload["template"], "overrides": payload.get("overrides", {}), "schedule_type": payload.get("schedule_type", "manual"), "timezone": payload.get("timezone", "UTC"), "hour": int(payload.get("hour", 8)), "minute": int(payload.get("minute", 0)), "weekday": int(payload.get("weekday", 0)), "interval_hours": int(payload.get("interval_hours", 1)), "notification_channels": payload.get("notification_channels", []), "alert_rules": payload.get("alert_rules", {}), "created_at": now, "updated_at": now, "last_run_at": None, "next_run_at": None, "last_status": "never_run", "last_workflow_id": ""}
    job["next_run_at"] = next_run_at(job)
    save_job(job)
    return job


def initialize_presets(timezone: str = "UTC") -> List[Dict[str, Any]]:
    """Explicit helper only. It never runs automatically and creates disabled jobs."""
    return [create_job({**preset, "enabled": False, "timezone": timezone}) for preset in PRESETS.values()]


def update_job(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    job = get_job(job_id)
    if not job:
        return None
    job.update({key: value for key, value in updates.items() if value is not None})
    job["next_run_at"] = next_run_at(job)
    save_job(job)
    return job


def next_run_at(job: Dict[str, Any], current: Optional[datetime] = None) -> Optional[str]:
    if job.get("schedule_type") == "manual" or not job.get("enabled", False):
        return None
    now = current or datetime.now(timezone.utc)
    zone = safe_zone(job.get("timezone", "UTC"))
    local = now.astimezone(zone).replace(second=0, microsecond=0)
    schedule = job.get("schedule_type", "daily")
    if schedule == "hourly":
        candidate = local.replace(minute=max(0, min(59, int(job.get("minute", 0)))))
        if candidate <= local:
            candidate += timedelta(hours=max(1, int(job.get("interval_hours", 1))))
    elif schedule == "weekly":
        candidate = local.replace(hour=max(0, min(23, int(job.get("hour", 8)))), minute=max(0, min(59, int(job.get("minute", 0)))))
        candidate += timedelta(days=(int(job.get("weekday", 0)) - candidate.weekday()) % 7)
        if candidate <= local:
            candidate += timedelta(days=7)
    else:
        candidate = local.replace(hour=max(0, min(23, int(job.get("hour", 8)))), minute=max(0, min(59, int(job.get("minute", 0)))))
        if candidate <= local:
            candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def due_jobs(current: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = current or datetime.now(timezone.utc)
    return [job for job in list_jobs() if job.get("enabled") and job.get("next_run_at") and parse_time(job["next_run_at"]) <= now]


async def run_job(job: Dict[str, Any], runner: WorkflowRunner, loader: WorkflowLoader, alert_saver: AlertSaver, notifier: Notifier, scheduled_at: str = "") -> Dict[str, Any]:
    scheduled_at = scheduled_at or job.get("next_run_at") or utc_now()
    execution_key = f"{job['id']}:{scheduled_at}"
    if has_execution_key(execution_key):
        return {"job_id": job["id"], "status": "skipped", "reason": "Duplicate scheduled execution prevented.", "execution_key": execution_key}
    run = {"id": str(uuid4()), "job_id": job["id"], "job_name": job["name"], "execution_key": execution_key, "scheduled_at": scheduled_at, "started_at": utc_now(), "completed_at": "", "status": "running", "workflow_id": "", "result_count": 0, "warnings": [], "alerts": [], "change_path": "", "notification_warnings": []}
    save_run(run)
    previous = next((item for item in list_runs(500) if item.get("job_id") == job["id"] and item.get("status") == "completed" and item.get("workflow_id")), None)
    try:
        workflow = await runner({"template": job["template"], "overrides": job.get("overrides", {})})
        run.update({"status": workflow["status"], "workflow_id": workflow["workflow_id"], "result_count": workflow["result_count"], "warnings": workflow.get("warnings", [])})
        change = compare_workflows(loader(previous["workflow_id"]) if previous else None, workflow, job["id"], run["id"])
        run["change_path"] = save_change(change)
        alerts = evaluate_alerts(job, run, workflow, change)
        for alert in alerts:
            alert_saver(alert)
        run["alerts"] = [alert["id"] for alert in alerts]
        run["notification_warnings"] = await notifier(job.get("notification_channels", []), notification_payload(job, run, workflow))
    except Exception as exc:
        run.update({"status": "failed", "warnings": ["Automation run failed: " + str(exc)]})
        alert = alert_payload(job, run, "workflow_failed", "Automation workflow failed.", "warning")
        alert_saver(alert)
        run["alerts"] = [alert["id"]]
    run["completed_at"] = utc_now()
    save_run(run)
    job.update({"last_run_at": run["completed_at"], "last_status": run["status"], "last_workflow_id": run["workflow_id"], "next_run_at": next_run_at(job)})
    save_job(job)
    return run


def compare_workflows(previous: Optional[Dict[str, Any]], current: Dict[str, Any], job_id: str, run_id: str) -> Dict[str, Any]:
    previous_results = previous.get("analysis", {}).get("top_results", []) if previous else []
    current_results = current.get("analysis", {}).get("top_results", [])
    previous_sources = {item.get("source", "") for item in previous_results}
    current_sources = {item.get("source", "") for item in current_results}
    previous_topics = {item.get("title", "") for item in previous.get("analysis", {}).get("key_findings", [])} if previous else set()
    current_topics = {item.get("title", "") for item in current.get("analysis", {}).get("key_findings", [])}
    return {"id": str(uuid4()), "job_id": job_id, "run_id": run_id, "created_at": utc_now(), "new_sources": sorted(current_sources - previous_sources), "removed_sources": sorted(previous_sources - current_sources), "new_topics": sorted(current_topics - previous_topics), "recurring_topics": sorted(current_topics & previous_topics), "keyword_count_change": len(current_topics) - len(previous_topics), "significant_score_changes": score_changes(previous_results, current_results), "newly_mentioned_platforms": sorted(current_sources - previous_sources)}


def evaluate_alerts(job: Dict[str, Any], run: Dict[str, Any], workflow: Dict[str, Any], change: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = job.get("alert_rules", {})
    text = " ".join([workflow.get("analysis", {}).get("executive_summary", "")] + [item.get("title", "") for item in workflow.get("analysis", {}).get("top_results", [])]).lower()
    results = workflow.get("analysis", {}).get("top_results", [])
    sources = {item.get("source", "") for item in results}
    alerts: List[Dict[str, Any]] = []
    for keyword in as_list(rules.get("new_keyword")):
        if keyword.lower() in text and keyword in change.get("new_topics", []) + change.get("recurring_topics", []): alerts.append(alert_payload(job, run, "new_keyword", f"Matched new keyword: {keyword}.") )
    if rules.get("result_count_above") is not None and run["result_count"] > int(rules["result_count_above"]): alerts.append(alert_payload(job, run, "result_count_above", "Result count is above configured threshold."))
    if rules.get("result_count_below") is not None and run["result_count"] < int(rules["result_count_below"]): alerts.append(alert_payload(job, run, "result_count_below", "Result count is below configured threshold.", "warning"))
    if rules.get("source_count_change") and (change["new_sources"] or change["removed_sources"]): alerts.append(alert_payload(job, run, "source_count_change", "Source set changed."))
    if rules.get("score_above") is not None and any(float(item.get("score") or 0) >= float(rules["score_above"]) for item in results): alerts.append(alert_payload(job, run, "score_above", "A result exceeded the configured score threshold."))
    if any(platform.lower() in {source.lower() for source in sources} for platform in as_list(rules.get("platform_mentioned"))): alerts.append(alert_payload(job, run, "platform_mentioned", "A configured platform was mentioned."))
    if rules.get("workflow_failed") and workflow.get("status") == "failed": alerts.append(alert_payload(job, run, "workflow_failed", "Workflow failed.", "warning"))
    if rules.get("warning_present") and workflow.get("warnings"): alerts.append(alert_payload(job, run, "warning_present", "Workflow returned warnings.", "warning"))
    return alerts


def alert_payload(job: Dict[str, Any], run: Dict[str, Any], rule: str, message: str, severity: str = "info") -> Dict[str, Any]:
    return {"id": str(uuid4()), "job_id": job["id"], "run_id": run["id"], "severity": severity, "rule": rule, "message": message, "created_at": utc_now(), "acknowledged": False, "related_workflow_id": run.get("workflow_id", ""), "monitor_id": "", "monitor_name": job["name"], "evidence": []}


def notification_payload(job: Dict[str, Any], run: Dict[str, Any], workflow: Dict[str, Any]) -> Dict[str, Any]:
    return {"job_name": job["name"], "run_status": run["status"], "workflow_id": run.get("workflow_id", ""), "result_count": run["result_count"], "warning_count": len(run["warnings"]), "alert_count": len(run["alerts"]), "summary": workflow.get("analysis", {}).get("executive_summary", "")[:400], "downloads": workflow.get("downloads", []), "dashboard_url": "/ui/automation"}


def safe_zone(value: str) -> ZoneInfo:
    try: return ZoneInfo(value)
    except ZoneInfoNotFoundError: return ZoneInfo("UTC")

def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def as_list(value: Any) -> List[str]:
    return [str(item) for item in value] if isinstance(value, list) else [str(value)] if value else []

def score_changes(previous: List[Dict[str, Any]], current: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    old = {item.get("url") or item.get("title"): float(item.get("score") or 0) for item in previous}
    return [{"title": item.get("title", ""), "previous_score": old[key], "current_score": float(item.get("score") or 0)} for item in current if (key := item.get("url") or item.get("title")) in old and abs(float(item.get("score") or 0) - old[key]) >= 1]
