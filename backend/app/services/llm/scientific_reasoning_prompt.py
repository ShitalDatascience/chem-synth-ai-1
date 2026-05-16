from typing import Dict, Any


class ScientificReasoningPrompt:

    @staticmethod
    def build(bundle: Dict[str, Any]) -> str:
        """
        Converts RAG bundle → scientist-grade reasoning prompt
        """

        chembl_id = bundle.get("chembl_id")
        targets = bundle.get("top_targets", [])
        assay_dist = bundle.get("assay_distribution", {})
        score = bundle.get("top_evidence_score", 0)
        samples = bundle.get("sample_evidence", [])

        return f"""
You are a senior medicinal chemist analyzing ChEMBL bioactivity evidence.

Your task is NOT summarization.

Your task is SCIENTIFIC REASONING.

========================
MOLECULE: {chembl_id}
========================

EVIDENCE SUMMARY:
- Top Targets: {targets}
- Assay Distribution: {assay_dist}
- Highest Evidence Score: {score}

SAMPLE EXPERIMENTAL DATA:
{samples}

========================
INSTRUCTIONS:
========================

1. Identify primary biologil mechanism (hypothesis level)
2. Explain which targets are most consistent and why
3. Interpret activity patterns across assays
4. Assess confidence in mechanism
5. Identify contradictions or noise in data
6. Provide a scientific conclusion

IMPORTANT:
- Do NOT copy data
- Do NOT just summarize
- Think like a drug discovery scientist
- Be precise, not verbose

OUTPUT FORMAT:

MECHANISM HYPOTHESIS:
...

TARGET ANALYSIS:
...

EVIDENCE CONSISTENCY:
...

CONFIDENCE ASSESSMENT:
...

LIMITATIONS:
...

FINAL CONCLUSION:
...
"""
