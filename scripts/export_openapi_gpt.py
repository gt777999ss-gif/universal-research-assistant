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
    ("/mcp/search", "post"),
    ("/mcp/analyze", "post"),
    ("/mcp/briefing", "post"),
)


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
    filtered["info"]["title"] = "Universal Research Assistant V9 GPT Actions API"
    filtered["info"]["description"] = (
        "ChatGPT Actions optimized OpenAPI specification for the Universal Research Assistant. "
        "This reduced schema keeps the most important public information research, agent, monitoring, "
        "reporting, and MCP wrapper operations under the ChatGPT Actions operation limit."
    )

    for path, method in INCLUDED_OPERATIONS:
        operation = full_schema["paths"][path][method]
        filtered["paths"].setdefault(path, {})[method] = copy.deepcopy(operation)

    operation_count = sum(len(methods) for methods in filtered["paths"].values())
    if operation_count != 23:
        raise RuntimeError(f"GPT OpenAPI operation count must be 23, got {operation_count}.")
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
