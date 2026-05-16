"""
Golden tests: narrative quality for the final report contract.

Architecture (no abstractions added here):
- ``generate_lora_report`` → narrative string only (used inside ``build_final_report``).
- ``build_final_report(ReportJSON)`` → ``FinalReport`` (source of truth for ``report_sections``).

Fixtures are assembled into ``ReportJSON`` the same way stored reports are passed into
``build_final_report`` in production.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from app.llm.schemas import (
    EvidenceSummary,
    MoleculeSection,
    PredictionEntry,
    ReportJSON,
    ReportSections,
    SimilarCompound,
)
from app.services.report_service import build_final_report

TESTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"

TEST_CASES = [
    "aspirin_case.json",
    "ibuprofen_case.json",
    "paracetamol_case.json",
    "celecoxib_case.json",
]

_NARRATIVE_SECTION_KEYS = (
    "executive_summary",
    "chembl_evidence",
    "predictions",
    "next_experiments",
)


def load_case(name: str) -> Dict[str, Any]:
    path = FIXTURES_DIR / name
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def report_from_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts fixture → ``ReportJSON`` (production-shaped input) → ``build_final_report`` → dict.

    ``build_final_report`` expects a ``ReportJSON`` instance, not a raw fixture dict; this helper
    maps fixture fields into that schema then returns ``FinalReport.model_dump()``.
    """
    mol = MoleculeSection(**case["molecule_data"])
    preds = [PredictionEntry(**p) for p in case["predictions"]]
    sims = [SimilarCompound(**s) for s in case.get("similar_compounds") or []]
    ev = EvidenceSummary(**case["evidence_summary"])
    rs = ReportSections(**case.get("report_sections", {}))
    rj = ReportJSON(
        report_id=case.get("report_id", "golden-test"),
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        query=case["query"],
        molecule=mol,
        similar_compounds=sims,
        evidence_summary=ev,
        experiment_list=list(case.get("experiment_list") or []),
        predictions=preds,
        report_sections=rs,
    )
    return build_final_report(rj).model_dump()


def assert_no_structured_leak(section_text: str, *, section: str = "section") -> None:
    """Section-level only: forbid JSON-ish fragments and braces in narrative fields."""
    forbidden_patterns = [
        '"target":',
        '"count":',
        '"value":',
        '"model_name":',
        "{",
        "}",
    ]
    for p in forbidden_patterns:
        assert p not in section_text, f"Structured leak {p!r} in {section}"


@pytest.fixture(autouse=True)
def _stable_lora_executive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic LoRA line so CI passes without adapter weights."""

    def _fake(
        molecule_data: Dict[str, Any],
        evidence_summary: Dict[str, Any],
        predictions: Any,
        report_sections: Dict[str, Any],
        similar_compounds: Any = None,
        experiment_list: Any = None,
    ) -> str:
        name = str(
            (molecule_data or {}).get("pref_name")
            or (molecule_data or {}).get("name")
            or "The compound"
        ).strip()
        return (
            f"{name} demonstrates substantial ChEMBL-backed annotation relevant to this review. "
            "Bioactivity concentrates on annotated cyclooxygenase-associated records suitable for medchem triage."
        )

    monkeypatch.setattr(
        "app.services.lora_report_service.generate_lora_report",
        _fake,
    )


def test_all_cases_narrative_sections_no_structured_leak() -> None:
    for case_name in TEST_CASES:
        report = report_from_case(load_case(case_name))
        rs = report["report_sections"]
        for key in _NARRATIVE_SECTION_KEYS:
            assert_no_structured_leak(str(rs.get(key) or ""), section=f"{case_name}:{key}")


def test_executive_summary_clean() -> None:
    report = report_from_case(load_case("aspirin_case.json"))
    section = report["report_sections"]["executive_summary"]

    assert isinstance(section, str)
    assert_no_structured_leak(section, section="executive_summary")

    parts = [p for p in section.split(".") if p.strip()]
    assert 2 <= len(parts) <= 6
    assert '"target"' not in section
    assert '"count"' not in section
    assert not re.search(r'["\']target["\']\s*:', section)


def test_chembl_evidence_clean() -> None:
    report = report_from_case(load_case("aspirin_case.json"))
    section = report["report_sections"]["chembl_evidence"]

    assert isinstance(section, str)
    assert_no_structured_leak(section, section="chembl_evidence")


def test_predictions_section_clean_and_narrative() -> None:
    report = report_from_case(load_case("aspirin_case.json"))
    section = report["report_sections"]["predictions"]

    assert isinstance(section, str)
    assert len(section) > 20
    assert_no_structured_leak(section, section="predictions")
    assert "0.837" not in section


def test_next_experiments_clean_and_bulleted() -> None:
    report = report_from_case(load_case("aspirin_case.json"))
    section = report["report_sections"]["next_experiments"]

    assert isinstance(section, str)
    assert_no_structured_leak(section, section="next_experiments")
    assert "•" in section or "-" in section
    assert '"target"' not in section
    assert "recommended_assay" not in section


def test_narrative_sections_sanity_per_section() -> None:
    """Sanity: each narrative field passes leak helper (no merged global JSON dump)."""
    report = report_from_case(load_case("aspirin_case.json"))
    rs = report["report_sections"]
    for key in _NARRATIVE_SECTION_KEYS:
        assert_no_structured_leak(str(rs.get(key) or ""), section=key)


def test_all_cases_roundtrip_final_report() -> None:
    for case_name in TEST_CASES:
        report = report_from_case(load_case(case_name))
        assert report["query"]
        rs = report["report_sections"]
        assert isinstance(rs.get("executive_summary"), str)
        assert len(rs.get("executive_summary", "")) > 20
