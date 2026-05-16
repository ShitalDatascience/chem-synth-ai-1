from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _to_markdown(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Scientific Report")
    lines.append("")

    # Pharma-grade hybrid blocks (preferred when present)
    for key, title in [
        ("bioactivity", "Bioactivity Prediction"),
        ("toxicity", "Toxicity Prediction"),
        ("solubility", "Solubility Prediction"),
    ]:
        block = report.get(key)
        if isinstance(block, dict) and "predicted_score" in block:
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- Predicted Score: {block.get('predicted_score')}")
            lines.append(f"- Confidence: {block.get('confidence')}")
            lines.append("")
            lines.append("Interpretation:")
            lines.append(str(block.get("interpretation", "")).strip())
            lines.append("")
            if block.get("decision_insight"):
                lines.append("Decision Insight:")
                lines.append(str(block.get("decision_insight", "")).strip())
                lines.append("")

    # Fallback: legacy 4-section text report
    for key in ["summary", "interpretation", "risk_assessment", "conclusion"]:
        if key in report:
            lines.append(f"## {key.replace('_', ' ').title()}")
            lines.append(str(report.get(key, "")).strip() or "")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def export_report(report: Dict[str, Any], format: str, output_path: str) -> str:
    """Export report to JSON or Markdown. PDF is placeholder interface."""
    fmt = (format or "json").lower().strip()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    envelope = {
        "report": report,
        "generated_at": _iso_now(),
        "model": report.get("model", "lora_report_writer_v1"),
    }

    if fmt in ("json", ".json"):
        out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(out)

    if fmt in ("md", "markdown", ".md"):
        md = _to_markdown(report)
        out.write_text(md, encoding="utf-8")
        return str(out)

    if fmt in ("pdf", ".pdf"):
        raise NotImplementedError("PDF export is not implemented yet (placeholder interface only).")

    raise ValueError(f"Unsupported export format: {format!r}")


__all__ = ["export_report"]

