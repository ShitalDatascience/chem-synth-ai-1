from __future__ import annotations

"""Thin wrapper around the unified RAG pipeline — returns the locked ``FinalReport`` dict."""

import logging
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


def generate_report(result: Dict[str, Any]) -> str:
    """Markdown summary from a ``FinalReport``-shaped dict."""
    query = result.get("query", "")
    similar = result.get("similar_compounds") or []
    preds = result.get("predictions") or []
    rs = result.get("report_sections") or {}

    lines: List[str] = []
    lines.append("## Query")
    lines.append(f"- {query}")
    lines.append("")
    lines.append("## Similar compounds")
    lines.append(f"- Count: {len(similar)}")
    for i, r in enumerate(similar[:10], start=1):
        lines.append(f"  - {i}. {r.get('chembl_id')} tanimoto={r.get('tanimoto')}")
    lines.append("")
    lines.append("## Predictions")
    lines.append(f"- {preds}")
    lines.append("")
    lines.append("## Report (sections)")
    lines.append(str(rs.get("executive_summary", ""))[:2000])
    return "\n".join(lines)


def generate_fingerprint(smiles: str) -> List[int]:
    """Bit vector as 0/1 list (length ``FP_NBITS``); delegates to :func:`rdkit_service.morgan_fp`."""
    from app.services import rdkit_service

    arr, _ = rdkit_service.morgan_fp(smiles)
    return [int(round(float(x))) for x in arr.tolist()]


def run_chem_agent(query: str, export_format: Optional[str] = None) -> Dict[str, Any]:
    from app.services.rag_orchestrator import run_pipeline_raw
    from app.services.report_service import assemble_report, build_final_report

    result = run_pipeline_raw(query)
    report = assemble_report(result)
    data = build_final_report(report).model_dump()

    if export_format:
        try:
            from datetime import datetime
            from pathlib import Path

            from app.training.report_lora_finetune import format_pharma_grade_report

            from app.services.report.exporter import export_report

            inner: Dict[str, float] = {}
            for p in data.get("predictions") or []:
                if not isinstance(p, dict):
                    continue
                t = (p.get("task") or "").lower()
                v = p.get("value")
                if isinstance(v, (int, float)):
                    if "solub" in t:
                        inner["solubility"] = float(v)
                    elif "tox" in t:
                        inner["toxicity"] = float(v)
            pharma = format_pharma_grade_report({"predictions": inner} if inner else {})

            fmt = export_format.lower().strip()
            ext = (
                "json"
                if fmt in ("json", ".json")
                else "md"
                if fmt in ("md", "markdown", ".md")
                else fmt.lstrip(".")
            )
            out_path = Path("data/exports") / f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{ext}"
            data["exported_file"] = export_report(pharma, export_format, str(out_path))
        except Exception as e:
            data["export_error"] = str(e)

    return data


__all__ = ["run_chem_agent", "generate_report", "generate_fingerprint"]
