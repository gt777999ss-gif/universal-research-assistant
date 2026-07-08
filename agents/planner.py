from __future__ import annotations

from typing import Any, Dict, List


def is_chinese_text(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def build_research_plan(
    goal: str,
    topics: List[str],
    sources: List[str],
    timeframe_days: int,
    output_language: str = "auto",
) -> Dict[str, Any]:
    language = resolve_language(goal, topics, output_language)
    normalized_topics = [topic.strip() for topic in topics if topic and topic.strip()]
    if not normalized_topics:
        normalized_topics = [goal]

    steps: List[Dict[str, Any]] = []
    step_id = 1
    for topic in normalized_topics:
        steps.append(
            {
                "step": step_id,
                "task": localized(language, f"Research recent public developments for {topic}.", f"研究 {topic} 的近期公开动态。"),
                "query": f"{topic} recent developments updates news discussions",
                "sources": sources,
                "reason": localized(
                    language,
                    f"Creates a focused evidence set for the topic within the last {timeframe_days} days.",
                    f"为该主题在最近 {timeframe_days} 天内建立聚焦证据集。",
                ),
            }
        )
        step_id += 1
        steps.append(
            {
                "step": step_id,
                "task": localized(language, f"Find public feedback, risks, and complaints for {topic}.", f"查找 {topic} 的公开反馈、风险和投诉。"),
                "query": f"{topic} user feedback risks complaints issues",
                "sources": sources,
                "reason": localized(language, "Captures weak signals, negative signals, and discussion quality.", "捕捉弱信号、负面信号和讨论质量。"),
            }
        )
        step_id += 1

    steps.append(
        {
            "step": step_id,
            "task": localized(language, "Compare repeated themes across all topics.", "比较所有主题中的重复主题。"),
            "query": f"{goal} trends comparison changes",
            "sources": sources,
            "reason": localized(language, "Detects cross-topic changes and recurring signals.", "识别跨主题变化和重复信号。"),
        }
    )

    return {
        "goal": goal,
        "research_plan": steps,
        "recommended_monitors": [
            {
                "name": f"{topic} Watch",
                "query": f"{topic} recent developments updates news discussions",
                "sources": sources,
                "frequency": "daily",
            }
            for topic in normalized_topics[:5]
        ],
        "recommended_reports": [
            {"type": "daily", "reason": localized(language, "Track short-term changes.", "跟踪短期变化。")},
            {"type": "weekly", "reason": localized(language, "Summarize broader trend movement.", "总结更广泛的趋势变化。")},
        ],
        "warnings": [],
    }


def resolve_language(goal: str, topics: List[str], output_language: str) -> str:
    if output_language.lower() != "auto":
        return output_language
    return "Chinese" if is_chinese_text(" ".join([goal] + topics)) else "English"


def localized(language: str, english: str, chinese: str) -> str:
    return chinese if language.lower() in {"chinese", "zh", "zh-cn"} else english

