from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List


def export_report(markdown: str, json_payload: Dict[str, Any], output_format: str) -> Dict[str, Any]:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    directory = Path("reports") / today
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%H%M%S")
    warnings: List[str] = []
    output_format = output_format.lower()
    if output_format == "markdown":
        path = directory / f"enterprise-report-{timestamp}.md"
        path.write_text(markdown, encoding="utf-8")
    elif output_format == "html":
        path = directory / f"enterprise-report-{timestamp}.html"
        path.write_text(markdown_to_html(markdown), encoding="utf-8")
    elif output_format == "json":
        path = directory / f"enterprise-report-{timestamp}.json"
        path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    elif output_format == "pdf":
        path = directory / f"enterprise-report-{timestamp}.md"
        path.write_text(markdown, encoding="utf-8")
        warnings.append("PDF export is a placeholder; Markdown was exported because PDF dependencies are not configured.")
    else:
        raise ValueError("Unsupported export format.")
    return {"format": output_format, "export_path": str(path), "download_url": "", "warnings": warnings}


def markdown_to_html(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            lines.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("- "):
            lines.append(f"<li>{escape(line[2:])}</li>")
        elif line.strip():
            lines.append(f"<p>{escape(line)}</p>")
    return "<!doctype html><html><head><meta charset='utf-8'><title>Research Report</title></head><body>" + "\n".join(lines) + "</body></html>"
