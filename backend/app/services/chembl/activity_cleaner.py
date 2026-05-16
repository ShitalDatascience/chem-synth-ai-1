import math
from decimal import Decimal
from typing import Dict, Any, Optional


class ActivityCleaner:
    """
    Phase 2: Normalization, Unit Conversion, and ML-ready cleaning layer.
    """

    UNIT_MAP = {
        "nM": 1.0,
        "uM": 1000.0,
        "µM": 1000.0,
        "mM": 1_000_000.0,
        "M": 1_000_000_000.0,
        "pM": 0.001,
    }

    # -----------------------------
    # SAFE TYPE CONVERSION
    # -----------------------------
    @staticmethod
    def to_float(value: Any) -> Optional[float]:
        """Convert Decimal / string / int safely to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # -----------------------------
    # UNIT NORMALIZATION
    # -----------------------------
    @classmethod
    def normalize_to_nm(cls, value: Any, unit: str) -> Optional[float]:
        """Convert concentration values to nM."""
        val_float = cls.to_float(value)

        if val_float is None or not unit:
            return None

        multiplier = cls.UNIT_MAP.get(unit)
        if multiplier is None:
            return None

        return val_float * multiplier

    # -----------------------------
    # MAIN CLEANING FUNCTION
    # -----------------------------
    @classmethod
    def clean_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert raw ChEMBL row → ML-ready structured format.
        """

        # Convert pChEMBL safely
        pchembl = cls.to_float(row.get("pchembl_value"))

        # Normalize activity value to nM
        value_nm = cls.normalize_to_nm(
            row.get("standard_value"),
            row.get("standard_units"),
        )

        # -----------------------------
        # FINAL CLEAN OUTPUT (CONTRACT)
        # -----------------------------
        return {
            "activity_id": row.get("activity_id"),

            # 🔥 CRITICAL FIX (was missing earlier)
            "target_chembl_id": row.get("target_chembl_id"),

            "standard_type": row.get("standard_type"),

            "value_nm": value_nm,

            "pchembl": pchembl,

            # ML usability flag
            "is_valid": value_nm is not None and value_nm > 0,
        }