from __future__ import annotations

"""ChemLLM client: wraps Ollama via LangChain ChatOllama.

Provides:
- classify_intent(query) → ToolPlan
- generate_report(evidence_bundle, predictions) → ReportSections
- Gated import: raises RuntimeError if langchain-ollama is not installed.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import get_settings
from app.llm.schemas import ReportSections, ToolPlan

logger = logging.getLogger(__name__)

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
    _LC_AVAILABLE = True
except ImportError:
    _LC_AVAILABLE = False
    logger.warning(
        "langchain-ollama not installed — ChemLLM calls will fall back to safe defaults"
    )


def _require_langchain() -> None:
    if not _LC_AVAILABLE:
        raise RuntimeError(
            "langchain-ollama is not installed. Run: uv add langchain langchain-ollama"
        )


def _load_prompt(name: str) -> str:
    base = Path(__file__).parent / "prompts"
    return (base / name).read_text(encoding="utf-8")


class ChemLLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self._model = s.chemllm_model
        self._base_url = s.ollama_base_url
        self._temperature = s.chemllm_temperature
        self._llm: Optional[Any] = None

    def _get_llm(self) -> Any:
        _require_langchain()
        if self._llm is None:
            self._llm = ChatOllama(
                model=self._model,
                base_url=self._base_url,
                temperature=self._temperature,
            )
            logger.info("ChemLLM connected: %s @ %s", self._model, self._base_url)
        return self._llm

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    def classify_intent(self, query: str) -> ToolPlan:
        """
        Use ChemLLM to classify intent and build a ToolPlan.
        Falls back to ToolPlan.safe_default if LLM is unavailable or returns invalid JSON.
        """
        if not _LC_AVAILABLE:
            logger.info("LangChain not available — using safe default tool plan")
            return ToolPlan.safe_default(query)

        try:
            template = _load_prompt("intent_classifier.txt").replace("{query}", query)
            llm = self._get_llm()
            response = llm.invoke([HumanMessage(content=template)])
            raw = response.content

            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                logger.warning("ChemLLM intent response has no JSON block — using fallback")
                return ToolPlan.safe_default(query)

            data = json.loads(json_match.group())
            return ToolPlan.model_validate(data)

        except Exception as exc:
            logger.warning("ChemLLM intent classification failed (%s) — using fallback", exc)
            return ToolPlan.safe_default(query)

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(
        self,
        evidence_bundle: Dict[str, Any],
        predictions: list,
        query: str = "",
    ) -> ReportSections:
        """
        Generate a structured medicinal chemistry report using ChemLLM.
        Returns ReportSections with populated text fields.
        """
        if not _LC_AVAILABLE:
            return ReportSections(
                executive_summary="[ChemLLM not available — report generation requires langchain-ollama]"
            )

        try:
            system_prompt = _load_prompt("system.txt")
            report_template = _load_prompt("report_template.txt")

            evidence_json = json.dumps(evidence_bundle, indent=2, default=str)[:12_000]
            pred_json = json.dumps(
                [p.model_dump() if hasattr(p, "model_dump") else p for p in predictions],
                indent=2,
                default=str,
            )[:3_000]

            user_prompt = report_template.replace(
                "{evidence_bundle}", evidence_json
            ).replace("{predictions}", pred_json)

            llm = self._get_llm()
            response = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            raw_report = response.content
            return _parse_report_sections(raw_report)

        except Exception as exc:
            logger.error("ChemLLM report generation failed: %s", exc)
            return ReportSections(
                executive_summary=f"[Report generation failed: {exc}]"
            )

    # ------------------------------------------------------------------
    # Verification pass
    # ------------------------------------------------------------------

    def verify_report(self, report_sections: ReportSections, evidence_bundle: Dict) -> ReportSections:
        """
        Lightweight consistency check: ensure claims in narrative are backed by evidence.
        Returns potentially corrected ReportSections.
        """
        if not _LC_AVAILABLE:
            return report_sections

        system_prompt = _load_prompt("system.txt")
        verify_prompt = f"""
Review the following medicinal chemistry report sections for consistency:
1. Ensure all targets mentioned in the narrative appear in the evidence bundle.
2. Ensure all potency values have units.
3. Ensure computational predictions are clearly labeled "Predicted".
4. If any claim is unsupported, mark it with [UNVERIFIED].

Report sections:
{report_sections.model_dump_json(indent=2)}

Evidence bundle summary (truncated):
{json.dumps(evidence_bundle, default=str)[:4000]}

Return corrected report sections in the same format.
"""
        try:
            llm = self._get_llm()
            response = llm.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=verify_prompt)]
            )
            return _parse_report_sections(response.content)
        except Exception as exc:
            logger.warning("Verify step failed: %s — returning unmodified report", exc)
            return report_sections


# ---------------------------------------------------------------------------
# Internal: parse LLM free-text into ReportSections
# ---------------------------------------------------------------------------

_SECTION_HEADINGS = {
    "executive_summary": r"###\s*Executive Summary",
    "molecular_identity": r"###\s*Molecular Identity",
    "physchem": r"###\s*Physicochemical Properties",
    "similar_compounds": r"###\s*Similar Compounds",
    "chembl_evidence": r"###\s*ChEMBL Experimental Evidence",
    "predictions": r"###\s*Predictions",
    "risks": r"###\s*Risks",
    "next_experiments": r"###\s*Recommended Next Experiments",
    "citations": r"###\s*Citations",
}


def _parse_report_sections(raw: str) -> ReportSections:
    """Split raw LLM output by section headings into ReportSections fields."""
    sections: dict[str, str] = {}
    keys = list(_SECTION_HEADINGS.keys())
    patterns = list(_SECTION_HEADINGS.values())

    positions: list[tuple[int, str]] = []
    for key, pat in zip(keys, patterns):
        for m in re.finditer(pat, raw, re.IGNORECASE):
            positions.append((m.end(), key))

    positions.sort(key=lambda x: x[0])

    for i, (start, key) in enumerate(positions):
        end = positions[i + 1][0] - len(raw) if i + 1 < len(positions) else len(raw)
        content = raw[start:end].strip()
        content = re.sub(r"^###.*\n?", "", content).strip()
        sections[key] = content

    if not sections:
        sections["executive_summary"] = raw.strip()

    return ReportSections(**sections)
