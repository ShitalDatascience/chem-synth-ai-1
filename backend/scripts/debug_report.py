#!/usr/bin/env python3
"""Print narrative sections for aspirin golden fixture (run from ``backend/``)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Assume cwd is backend/
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.llm.schemas import (  # noqa: E402
    EvidenceSummary,
    MoleculeSection,
    PredictionEntry,
    ReportJSON,
    ReportSections,
    SimilarCompound,
)
from app.services.report_service import build_final_report  # noqa: E402


def main() -> None:
    fixture = BACKEND / "tests" / "fixtures" / "aspirin_case.json"
    with fixture.open(encoding="utf-8") as f:
        data = json.load(f)

    mol = MoleculeSection(**data["molecule_data"])
    preds = [PredictionEntry(**p) for p in data["predictions"]]
    sims = [SimilarCompound(**s) for s in data.get("similar_compounds") or []]
    ev = EvidenceSummary(**data["evidence_summary"])
    rs = ReportSections(**data.get("report_sections", {}))
    rj = ReportJSON(
        report_id=data.get("report_id", "debug"),
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        query=data["query"],
        molecule=mol,
        similar_compounds=sims,
        evidence_summary=ev,
        experiment_list=list(data.get("experiment_list") or []),
        predictions=preds,
        report_sections=rs,
    )
    report = build_final_report(rj).model_dump()
    sections = report["report_sections"]

    print("\n===== EXECUTIVE =====\n")
    print(sections.get("executive_summary", ""))

    print("\n===== PREDICTIONS =====\n")
    print(sections.get("predictions", ""))

    print("\n===== NEXT EXPERIMENTS =====\n")
    print(sections.get("next_experiments", ""))


if __name__ == "__main__":
    main()
