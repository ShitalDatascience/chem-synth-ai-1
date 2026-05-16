from __future__ import annotations

"""Milestone 5 — dataset builder for LoRA report style tuning.

Converts Phase 4 agent outputs into JSONL training rows:
{
  "input": {"evidence_summary": "...", "predictions": {...}, "similarity": [...]},
  "output": {"report_sections": {"summary": "...", "interpretation": "...", "risk_assessment": "...", "conclusion": "..."}}
}
"""

import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_OUT_PATH = Path("data/training/report_dataset.jsonl")


def build_training_dataset(raw_outputs: List[Dict[str, Any]], out_path: str | None = None) -> str:
    """Build JSONL dataset file from Phase 4 outputs. Returns file path."""
    path = Path(out_path) if out_path else DEFAULT_OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for r in raw_outputs:
            # Keep content strictly grounded in pipeline outputs.
            evidence_summary = (
                (r.get("final_report") or {}).get("summary")
                or (r.get("final_summary") or "")
                or ""
            )

            predictions = (
                r.get("deepchem_prediction")
                or r.get("deepchem_prediction", {})
                or {}
            )
            similarity = r.get("similar_molecules") or r.get("retrieved_molecules") or []

            report_sections = (r.get("final_report_sections") or r.get("report_sections") or {}) if isinstance(r, dict) else {}

            row = {
                "input": {
                    "evidence_summary": str(evidence_summary),
                    "predictions": predictions,
                    "similarity": similarity,
                },
                "output": {
                    "report_sections": {
                        "summary": str(report_sections.get("summary", "")),
                        "interpretation": str(report_sections.get("interpretation", "")),
                        "risk_assessment": str(report_sections.get("risk_assessment", "")),
                        "conclusion": str(report_sections.get("conclusion", "")),
                    }
                },
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return str(path)


__all__ = ["build_training_dataset"]

