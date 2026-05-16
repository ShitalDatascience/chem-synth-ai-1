import logging
from typing import Any, Dict, Optional

from app.services.chembl_service import ChemblService

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    _RDKIT_AVAILABLE = True
except ImportError:
    _RDKIT_AVAILABLE = False
    logger.warning("rdkit not installed — NormalizationService SMILES detection disabled")


def resolve_drug_name(name: str) -> Optional[Dict[str, Any]]:
    from app.services.chembl_service import ChemblService

    svc = ChemblService()

    mol = svc.get_molecule_by_pref_name(name)
    if mol and mol.get("canonical_smiles"):
        return mol

    rows = svc.search_by_name(name, limit=10)
    for row in rows or []:
        cid = row.get("chembl_id")
        full = svc.get_by_chembl_id(cid) if cid else None
        if full and full.get("canonical_smiles"):
            return full

    return None


class NormalizationService:
    """
    Converts user input → standardized molecular representation
    WITHOUT breaking pipeline.
    """

    chembl_service = ChemblService()

    @staticmethod
    def detect_input(query: str) -> Dict[str, str]:
        query = query.strip()

        if _RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(query)
            if mol:
                return {"type": "smiles", "value": query}

        if query.upper().startswith("CHEMBL"):
            return {"type": "chembl_id", "value": query.upper()}

        if query.isalpha() and query.isupper():
            return {"type": "target", "value": query}

        return {"type": "drug_name", "value": query}

    @classmethod
    def resolve(cls, query: str) -> Dict[str, Any]:
        detected = cls.detect_input(query)
        qtype = detected["type"]
        value = detected["value"]

        if qtype == "smiles":
            out: Dict[str, Any] = {"canonical_smiles": value, "input_type": "smiles"}
            mol_row = cls.chembl_service.get_molecule_by_canonical_smiles(value)
            cid = (mol_row or {}).get("chembl_id")
            if cid:
                out["chembl_id"] = str(cid).upper()
            return out

        if qtype == "chembl_id":
            mol = cls.chembl_service.get_by_chembl_id(value)
            if mol:
                return {
                    "canonical_smiles": mol.get("canonical_smiles"),
                    "input_type": "chembl_id",
                    "chembl_id": value,
                }

        if qtype == "drug_name":
            mol = resolve_drug_name(value)
            if mol:
                out: Dict[str, Any] = {
                    "canonical_smiles": mol["canonical_smiles"],
                    "input_type": "drug_name",
                    "name": value,
                }
                cid = mol.get("chembl_id")
                if cid:
                    out["chembl_id"] = str(cid).upper()
                return out

        if qtype == "target":
            return {
                "canonical_smiles": None,
                "input_type": "target",
                "target": value,
            }

        return {"canonical_smiles": None, "input_type": qtype, "name": value}
