from typing import Dict, Any, List, Optional


class EvidenceNormalizer:

    # ----------------------------
    # 1. UNIT CONVERSION TO nM
    # ----------------------------
    @staticmethod
    def to_nanomolar(value: float, unit: str) -> Optional[float]:
        if value is None:
            return None

        unit_lc = (unit or "").strip().lower()
        # Unicode micro sign → ASCII u for consistent matching (µM / μM → uM)
        u_compact = unit_lc.replace(" ", "").replace("μ", "u")

        try:
            value = float(value)
        except (TypeError, ValueError):
            return None

        # Conversions → nM (per ChEMBL-style concentration units)
        if u_compact == "nm" or u_compact.startswith("nm") or "nmol" in u_compact:
            return value
        if (
            u_compact in ("um", "µm", "μm")
            or (u_compact.endswith("um") and not u_compact.startswith("nm"))
            or "umol" in u_compact
            or "micromolar" in unit_lc
        ):
            return value * 1000.0
        if u_compact == "mm" or "mmol" in u_compact or "millimolar" in unit_lc:
            return value * 1_000_000.0
        if u_compact == "pm" or "pmol" in u_compact:
            return value / 1000.0

        return None

    # ----------------------------
    # 2. STANDARDIZE ASSAY TYPE
    # ----------------------------
    @staticmethod
    def normalize_type(raw_type: str) -> str:
        if not raw_type:
            return "UNKNOWN"

        t = raw_type.lower()

        if "ic50" in t:
            return "IC50"
        if "ki" in t:
            return "Ki"
        if "ec50" in t:
            return "EC50"
        if "kd" in t:
            return "Kd"

        return raw_type.upper()

    # ----------------------------
    # 3. CLEAN ONE ROW
    # ----------------------------
    @staticmethod
    def normalize_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:

        value = row.get("standard_value")
        unit = row.get("standard_units")

        value_nM = EvidenceNormalizer.to_nanomolar(value, unit)

        if value_nM is None:
            return None

        assay_type = EvidenceNormalizer.normalize_type(
            row.get("standard_type")
        )

        confidence = row.get("confidence_score") or 0

        return {
            "activity_id": row.get("activity_id"),
            "assay_id": row.get("assay_id"),
            "target": row.get("target_pref_name") or row.get("target_chembl_id"),
            "type": assay_type,
            "value_nM": round(value_nM, 4),
            "confidence": confidence,
            "is_high_quality": confidence >= 7
        }

    # ----------------------------
    # 4. NORMALIZE FULL LIST
    # ----------------------------
    @staticmethod
    def normalize_evidence(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        clean = []

        for r in rows:
            nr = EvidenceNormalizer.normalize_row(r)
            if nr:
                clean.append(nr)

        return clean
