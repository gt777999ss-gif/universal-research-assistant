from __future__ import annotations

from typing import Any, Dict, List

from agents.planner import localized


def build_agent_briefing(
    goal: str,
    plan: List[Dict[str, Any]],
    executed_queries: List[str],
    analysis: Dict[str, Any],
    language: str,
) -> str:
    lines = [f"# {localized(language, 'Autonomous Research Briefing', '自主研究简报')}", "", f"## {localized(language, 'Goal', '目标')}", "", goal, ""]
    lines.extend([f"## {localized(language, 'Executive Summary', '执行摘要')}", "", analysis.get("executive_summary", ""), ""])
    lines.extend([f"## {localized(language, 'Executed Queries', '已执行查询')}", ""])
    lines.extend(f"- {query}" for query in executed_queries)
    lines.extend(["", f"## {localized(language, 'Key Findings', '关键发现')}", ""])
    for item in analysis.get("key_findings", [])[:8]:
        lines.append(f"- **{item.get('title', '')}**: {item.get('summary', '')}")
    lines.extend(["", f"## {localized(language, 'Risks', '风险')}", ""])
    for item in analysis.get("risks", [])[:5]:
        lines.append(f"- **{item.get('risk', '')}**: {item.get('explanation', '')}")
    lines.extend(["", f"## {localized(language, 'Opportunities', '机会')}", ""])
    for item in analysis.get("opportunities", [])[:5]:
        lines.append(f"- **{item.get('opportunity', '')}**: {item.get('explanation', '')}")
    lines.extend(["", f"## {localized(language, 'Recommended Next Steps', '建议下一步')}", ""])
    lines.extend(f"- {item}" for item in recommended_next_steps(goal, language))
    return "\n".join(lines) + "\n"


def recommended_next_steps(goal: str, language: str) -> List[str]:
    if language.lower() in {"chinese", "zh", "zh-cn"}:
        return [f"继续监控“{goal}”的新增公开信息。", "对高频主题建立单独监控。", "每周比较趋势、风险和机会变化。"]
    return [f"Continue monitoring new public information for '{goal}'.", "Create dedicated monitors for high-frequency topics.", "Compare trend, risk, and opportunity movement weekly."]

