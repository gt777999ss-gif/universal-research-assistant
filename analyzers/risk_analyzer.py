from __future__ import annotations

from typing import Any, Dict, List


RISK_TERMS = [
    "risk", "concern", "complaint", "problem", "issue", "lawsuit", "ban",
    "unsafe", "privacy", "security", "scam", "fake", "broken", "refund",
    "投诉", "风险", "问题", "担忧", "隐私", "安全", "诈骗", "退款",
]


def analyze_risks(results: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    for term in RISK_TERMS:
        evidence = [
            item.get("title", "")
            for item in results
            if term.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower()
        ][:3]
        if evidence:
            risks.append(
                {
                    "risk": term,
                    "explanation": f"Potential negative signal found around '{term}'.",
                    "evidence": evidence,
                }
            )
        if len(risks) >= limit:
            break
    return risks
