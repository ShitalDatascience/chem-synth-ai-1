"""Rule-based query intent for the query orchestrator (no ML, no external I/O)."""

from __future__ import annotations

_REPORT_SUBSTRINGS = (
    "report",
    "summary",
    "analysis",
    "generate report",
)


def detect_flow_mode(query: str) -> str:
    """
    Map free text to a coarse flow label.

    Returns:
        ``\"report\"`` when report-style intent is detected, else ``\"chat\"``.
    """
    q = (query or "").lower()
    for token in _REPORT_SUBSTRINGS:
        if token in q:
            return "report"
    return "chat"
