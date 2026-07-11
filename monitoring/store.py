from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


MONITOR_DIR = Path("data/monitors")
HISTORY_DIR = Path("data/history")
ALERT_DIR = Path("data/alerts")
REPORTS_DIR = Path("reports")

FREQUENCY_DELTAS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def ensure_runtime_dirs() -> None:
    MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def create_monitor(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_runtime_dirs()
    now = utc_now().isoformat() + "Z"
    monitor = {
        **payload,
        "id": payload.get("id") or str(uuid4()),
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
        "last_run": payload.get("last_run"),
        "next_run": payload.get("next_run") or next_run_time(payload.get("frequency", "daily"), utc_now()),
        "last_status": payload.get("last_status") or "never_run",
        "last_warning_count": payload.get("last_warning_count") or 0,
    }
    save_monitor(monitor)
    return monitor


def save_monitor(monitor: Dict[str, Any]) -> None:
    ensure_runtime_dirs()
    monitor["updated_at"] = utc_now().isoformat() + "Z"
    (MONITOR_DIR / f"{monitor['id']}.json").write_text(json.dumps(monitor, indent=2, ensure_ascii=False), encoding="utf-8")


def update_monitor(monitor_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    monitor = get_monitor(monitor_id)
    if not monitor:
        return None
    monitor.update({key: value for key, value in updates.items() if value is not None})
    save_monitor(monitor)
    return monitor


def list_monitors() -> List[Dict[str, Any]]:
    ensure_runtime_dirs()
    monitors = []
    for path in sorted(MONITOR_DIR.glob("*.json")):
        monitors.append(json.loads(path.read_text(encoding="utf-8")))
    return monitors


def get_monitor(monitor_id: str) -> Optional[Dict[str, Any]]:
    path = MONITOR_DIR / f"{monitor_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_monitor(monitor_id: str) -> bool:
    path = MONITOR_DIR / f"{monitor_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def enabled_due_monitors(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or utc_now()
    due = []
    for monitor in list_monitors():
        if not monitor.get("enabled", True):
            continue
        next_run = parse_time(monitor.get("next_run"))
        if next_run is None or next_run <= now:
            due.append(monitor)
    return due


def update_monitor_after_run(monitor: Dict[str, Any], status: str, warning_count: int) -> Dict[str, Any]:
    now = utc_now()
    monitor["last_run"] = now.isoformat() + "Z"
    monitor["next_run"] = next_run_time(monitor.get("frequency", "daily"), now)
    monitor["last_status"] = status
    monitor["last_warning_count"] = warning_count
    save_monitor(monitor)
    return monitor


def save_history(monitor_id: str, record: Dict[str, Any]) -> str:
    ensure_runtime_dirs()
    timestamp = utc_now().strftime("%Y%m%d-%H%M%S")
    path = HISTORY_DIR / f"{monitor_id}-{timestamp}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def save_alert(alert: Dict[str, Any]) -> str:
    ensure_runtime_dirs()
    timestamp = utc_now().strftime("%Y%m%d-%H%M%S-%f")
    path = ALERT_DIR / f"alert-{timestamp}.json"
    payload = {"created_at": utc_now().isoformat() + "Z", "acknowledged": False, **alert}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def list_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    ensure_runtime_dirs()
    files = sorted(ALERT_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    alerts: List[Dict[str, Any]] = []
    for path in files[:limit]:
        item = json.loads(path.read_text(encoding="utf-8"))
        item["path"] = str(path)
        alerts.append(item)
    return alerts


def acknowledge_alert(alert_id: str) -> Optional[Dict[str, Any]]:
    if "/" in alert_id or ".." in alert_id:
        return None
    ensure_runtime_dirs()
    for path in ALERT_DIR.glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("id") == alert_id:
            item["acknowledged"] = True
            item["acknowledged_at"] = utc_now().isoformat() + "Z"
            path.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
            item["path"] = str(path)
            return item
    return None


def save_report_files(
    report_name: str,
    json_payload: Dict[str, Any],
    markdown: str,
    csv_path: str = "",
) -> Dict[str, str]:
    ensure_runtime_dirs()
    day_dir = REPORTS_DIR / utc_now().strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().strftime("%H%M%S")
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in report_name.lower())[:80]
    json_file = day_dir / f"{safe_name}-{stamp}.json"
    md_file = day_dir / f"{safe_name}-{stamp}.md"
    json_file.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_file.write_text(markdown, encoding="utf-8")
    paths = {"json": str(json_file), "markdown": str(md_file)}
    if csv_path:
        paths["csv"] = csv_path
    return paths


def recent_reports(limit: int = 10) -> List[Dict[str, Any]]:
    ensure_runtime_dirs()
    files = sorted(REPORTS_DIR.glob("*/*.*"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [report_file_info(path) for path in files[:limit]]


def list_report_dates() -> List[str]:
    ensure_runtime_dirs()
    return sorted([path.name for path in REPORTS_DIR.iterdir() if path.is_dir()], reverse=True)


def reports_for_date(report_date: str) -> List[Dict[str, Any]]:
    day_dir = REPORTS_DIR / report_date
    if not day_dir.exists() or not day_dir.is_dir():
        return []
    return [report_file_info(path) for path in sorted(day_dir.glob("*.*"), key=lambda item: item.stat().st_mtime, reverse=True)]


def report_file_info(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path),
        "date": path.parent.name,
        "name": path.name,
        "type": path.suffix.lstrip("."),
        "size_bytes": path.stat().st_size,
        "download_url": f"/reports/download/{path.parent.name}/{path.name}",
    }


def load_report_json(report_date: str) -> Optional[Dict[str, Any]]:
    day_dir = REPORTS_DIR / report_date
    if not day_dir.exists():
        return None
    files = sorted(day_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def next_run_time(frequency: str, from_time: datetime) -> str:
    delta = FREQUENCY_DELTAS.get(frequency, FREQUENCY_DELTAS["daily"])
    return (from_time + delta).isoformat() + "Z"


def parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None
