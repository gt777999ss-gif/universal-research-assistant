from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


WORKFLOW_DIR = Path("data/workflows")


def ensure_workflow_dir() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)


def save_workflow(workflow: Dict[str, Any]) -> str:
    ensure_workflow_dir()
    workflow["updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    path = WORKFLOW_DIR / f"{workflow['workflow_id']}.json"
    path.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    if "/" in workflow_id or ".." in workflow_id:
        return None
    path = WORKFLOW_DIR / f"{workflow_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_workflows(limit: int = 50) -> List[Dict[str, Any]]:
    ensure_workflow_dir()
    files = sorted(WORKFLOW_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return [json.loads(path.read_text(encoding="utf-8")) for path in files[:limit]]
