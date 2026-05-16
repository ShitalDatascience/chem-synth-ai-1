from typing import Dict, Any
import requests
import json


class RAGLLM:

    @staticmethod
    def generate(bundle: Dict[str, Any]) -> Dict[str, Any]:
        mol = bundle.get("molecule") or {}
        smi = (
            (mol.get("canonical_smiles") or mol.get("smiles") or "")
            if isinstance(mol, dict)
            else ""
        ).strip()
        if not smi:
            return {
                "chembl_id": bundle.get("chembl_id"),
                "summary": "LLM skipped: incomplete bundle",
                "key_targets": [],
                "evidence_interpretation": "",
                "bioactivity_insight": "",
                "confidence_note": "",
                "limitations": "Missing molecule SMILES in bundle; cannot generate grounded text.",
            }
        if bundle.get("evidence_summary") is None or bundle.get("predictions") is None:
            return {
                "chembl_id": bundle.get("chembl_id"),
                "summary": "LLM skipped: incomplete bundle",
                "key_targets": [],
                "evidence_interpretation": "",
                "bioactivity_insight": "",
                "confidence_note": "",
                "limitations": "Bundle must include evidence_summary and predictions keys (use [] / {}).",
            }

        # -----------------------------
        # STRICT SCIENTIFIC PROMPT
        # -----------------------------
        prompt = f"""
You are a STRICT scientific reasoning engine for drug discovery.

You are NOT a chatbot.

You MUST ONLY use the provided evidence bundle.

ABSOLUTE RULES:
- Output ONLY valid JSON
- No explanations
- No markdown
- No extra text
- Do NOT omit required fields
- If unknown, use "unknown" or []

---

INPUT DATA:
{json.dumps(bundle, indent=2, default=str)}

---

OUTPUT FORMAT (STRICT JSON ONLY):

{{
  "chembl_id": "CHEMBL ID from input",
  "summary": "1-3 line scientific interpretation of bioactivity profile",
  "key_targets": ["CHEMBL target IDs from evidence"],
  "evidence_interpretation": "what experimental data suggests",
  "bioactivity_insight": "potency / mechanism interpretation",
  "confidence_note": "low / medium / high based on evidence density",
  "limitations": "missing data or assay limitations"
}}
"""

        try:
            # -----------------------------
            # CALL OLLAMA
            # -----------------------------
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=120
            )

            # -----------------------------
            # HANDLE API FAILURE
            # -----------------------------
            if response.status_code != 200:
                return {
                    "chembl_id": bundle.get("chembl_id"),
                    "summary": "LLM error: Ollama not responding",
                    "key_targets": [],
                    "evidence_interpretation": "",
                    "bioactivity_insight": "",
                    "confidence_note": "",
                    "limitations": "Ollama API failure"
                }

            raw = response.json().get("response", "").strip()

            # -----------------------------
            # EXTRACT JSON BLOCK SAFELY
            # -----------------------------
            if "{" in raw and "}" in raw:
                raw = raw[raw.find("{"): raw.rfind("}") + 1]

            parsed = json.loads(raw)

            # -----------------------------
            # SAFE OUTPUT NORMALIZATION
            # -----------------------------
            return {
                "chembl_id": parsed.get("chembl_id", bundle.get("chembl_id")),
                "summary": parsed.get("summary", "unknown"),
                "key_targets": parsed.get("key_targets", []),
                "evidence_interpretation": parsed.get("evidence_interpretation", "unknown"),
                "bioactivity_insight": parsed.get("bioactivity_insight", "unknown"),
                "confidence_note": parsed.get("confidence_note", "unknown"),
                "limitations": parsed.get("limitations", "unknown")
            }

        except Exception as e:
            # -----------------------------
            # FINAL FALLBACK SAFETY LAYER
            # -----------------------------
            return {
                "chembl_id": bundle.get("chembl_id"),
                "summary": "LLM parsing failed",
                "key_targets": [],
                "evidence_interpretation": "",
                "bioactivity_insight": "",
                "confidence_note": "",
                "limitations": f"Error: {str(e)}"
            }