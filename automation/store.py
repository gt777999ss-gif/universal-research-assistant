from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path("data/automation")
JOB_DIR = BASE_DIR / "jobs"
RUN_DIR = BASE_DIR / "runs"
CHANGE_DIR = BASE_DIR / "changes"


def ensure_dirs() -> None:
    for directory in (JOB_DIR, RUN_DIR, CHANGE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def save_json(directory: Path, key: str, payload: Dict[str, Any]) -> str:
    ensure_dirs()
    path = directory / f"{key}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def load_json(directory: Path, key: str) -> Optional[Dict[str, Any]]:
    if "/" in key or ".." in key:
        return None
    path = directory / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_json(directory: Path, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_dirs()
    files = sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return [json.loads(path.read_text(encoding="utf-8")) for path in files[:limit]]


def save_job(job: Dict[str, Any]) -> str:
    job["updated_at"] = utc_now()
    return save_json(JOB_DIR, job["id"], job)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return load_json(JOB_DIR, job_id)


def list_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    return list_json(JOB_DIR, limit)


def delete_job(job_id: str) -> bool:
    path = JOB_DIR / f"{job_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def save_run(run: Dict[str, Any]) -> str:
    return save_json(RUN_DIR, run["id"], run)


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    return load_json(RUN_DIR, run_id)


def list_runs(limit: int = 100) -> List[Dict[str, Any]]:
    return list_json(RUN_DIR, limit)


def has_execution_key(execution_key: str) -> bool:
    return any(item.get("execution_key") == execution_key for item in list_runs(1000))


def save_change(change: Dict[str, Any]) -> str:
    return save_json(CHANGE_DIR, change["id"], change)


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
