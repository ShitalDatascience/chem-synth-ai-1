from typing import List, Dict, Any


class EvidenceScorer:

    # ----------------------------
    # 1. ASSAY PRIORITY
    # ----------------------------
    @staticmethod
    def assay_weight(assay_type: str) -> float:
        t = (assay_type or "").upper()

        if t == "IC50":
            return 1.0
        if t == "KI":
            return 0.95
        if t == "EC50":
            return 0.85
        if t == "KD":
            return 0.8

        return 0.5

    # ----------------------------
    # 2. POTENCY SCORE (LOWER nM = BETTER)
    # ----------------------------
    @staticmethod
    def potency_score(value_nM: float) -> float:
        if not value_nM or value_nM <= 0:
            return 0.0

        # log scaling (very important in bioactivity)
        import math
        return max(0.0, 1 / (1 + math.log10(value_nM)))

    # ----------------------------
    # 3. FINAL SCORE
    # ----------------------------
    @staticmethod
    def score_row(row: Dict[str, Any]) -> float:

        potency = EvidenceScorer.potency_score(row.get("value_nM"))
        assay = EvidenceScorer.assay_weight(row.get("type"))
        confidence = (row.get("confidence") or 0) / 10.0

        return round(
            (0.5 * potency) +
            (0.3 * assay) +
            (0.2 * confidence),
            4
        )

    # ----------------------------
    # 4. SCORE ALL + SORT
    # ----------------------------
    @staticmethod
    def rank_evidence(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        scored = []

        for r in rows:
            r = dict(r)
            r["evidence_score"] = EvidenceScorer.score_row(r)
            scored.append(r)

        return sorted(scored, key=lambda x: x["evidence_score"], reverse=True)
