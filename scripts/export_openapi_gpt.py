from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any, Dict, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app


INCLUDED_OPERATIONS: Tuple[Tuple[str, str], ...] = (
    ("/health", "get"),
    ("/sources", "get"),
    ("/search", "post"),
    ("/analyze", "post"),
    ("/report", "post"),
    ("/report/export", "post"),
    ("/batch", "post"),
    ("/agent/plan", "post"),
    ("/agent/run", "post"),
    ("/agent/changes", "post"),
    ("/agent/briefing", "post"),
    ("/monitors", "get"),
    ("/monitors", "post"),
    ("/monitors/{id}", "put"),
    ("/monitors/{id}", "delete"),
    ("/monitor/run", "post"),
    ("/alerts", "get"),
    ("/scheduler", "get"),
    ("/reports", "get"),
    ("/reports/{date}", "get"),
    ("/research/run", "post"),
    ("/research/workflows", "get"),
    ("/research/workflows/{workflow_id}", "get"),
    ("/research/templates", "get"),
    ("/research/run-template", "post"),
    ("/mcp/search", "post"),
    ("/mcp/analyze", "post"),
    ("/mcp/briefing", "post"),
)

EXPLICIT_OBJECT_PROPERTIES: Dict[str, Dict[str, Any]] = {
    "alert_rules": {
        "new_keyword": {"type": "boolean"},
        "trend_spike": {"type": "boolean"},
        "source_updated": {"type": "boolean"},
        "competitor_mentioned": {"type": "boolean"},
    },
    "recommended_monitors": {"name": {"type": "string"}, "query": {"type": "string"}},
    "recommended_reports": {"report_type": {"type": "string"}, "query": {"type": "string"}},
    "recent_reports": {"date": {"type": "string"}, "title": {"type": "string"}, "path": {"type": "string"}},
    "recent_alerts": {"message": {"type": "string"}, "severity": {"type": "string"}, "created_at": {"type": "string"}},
    "scheduler_status": {"running": {"type": "boolean"}, "enabled_monitors": {"type": "integer"}},
    "tools": {"name": {"type": "string"}, "description": {"type": "string"}},
    "results": {"monitor_id": {"type": "string"}, "report_path": {"type": "string"}, "status": {"type": "string"}},
    "json_report": {"executive_summary": {"type": "string"}, "top_stories": {"type": "array", "items": {"type": "string"}}},
    "export_paths": {"markdown": {"type": "string"}, "html": {"type": "string"}, "json": {"type": "string"}, "csv": {"type": "string"}},
    "exports": {"csv": {"type": "string"}, "markdown": {"type": "string"}},
    "analysis": {"executive_summary": {"type": "string"}, "warnings": {"type": "array", "items": {"type": "string"}}},
    "ctx": {"field": {"type": "string"}, "message": {"type": "string"}},
    "Response Deleteenterprisemonitor": {"success": {"type": "boolean"}, "message": {"type": "string"}},
}


def explicit_properties(key: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Describe dynamic backend dictionaries with ChatGPT Actions-safe fields."""
    name = schema.get("title", key)
    return copy.deepcopy(EXPLICIT_OBJECT_PROPERTIES.get(name, EXPLICIT_OBJECT_PROPERTIES.get(key, {
        "data": {"type": "string", "description": "Serialized response data."},
    })))


def normalize_object_schemas(value: Any, key: str = "") -> None:
    """Remove dynamic object maps, which the ChatGPT Actions importer rejects."""
    if isinstance(value, dict):
        if value.get("type") == "object":
            value.pop("additionalProperties", None)
            if not value.get("properties"):
                value["properties"] = explicit_properties(key, value)
        for child_key, child in value.items():
            normalize_object_schemas(child, child_key)
    elif isinstance(value, list):
        for child in value:
            normalize_object_schemas(child, key)


def build_gpt_openapi() -> Dict[str, Any]:
    full_schema = app.openapi()
    filtered = copy.deepcopy(full_schema)
    filtered["paths"] = {}
    filtered["servers"] = [
        {
            "url": "https://universal-research-assistant.onrender.com",
            "description": "Production server",
        }
    ]
    filtered["info"]["title"] = "Universal Research Assistant V10 GPT Actions API"
    filtered["info"]["description"] = (
        "ChatGPT Actions optimized OpenAPI specification for the Universal Research Assistant. "
        "This reduced schema keeps the most important public information research, agent, monitoring, "
        "reporting, and MCP wrapper operations under the ChatGPT Actions operation limit."
    )

    for path, method in INCLUDED_OPERATIONS:
        operation = full_schema["paths"][path][method]
        filtered["paths"].setdefault(path, {})[method] = copy.deepcopy(operation)

    normalize_object_schemas(filtered)

    operation_count = sum(len(methods) for methods in filtered["paths"].values())
    if operation_count != 28:
        raise RuntimeError(f"GPT OpenAPI operation count must be 28, got {operation_count}.")
    return filtered


def main() -> None:
    schema = build_gpt_openapi()
    json_path = ROOT / "openapi_gpt.json"
    yaml_path = ROOT / "openapi_gpt.yaml"
    json_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    yaml_path.write_text(yaml.safe_dump(schema, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {yaml_path}")


if __name__ == "__main__":
    main()
