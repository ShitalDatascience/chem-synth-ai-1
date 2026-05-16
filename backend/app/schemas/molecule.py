from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MoleculeIdentity(BaseModel):
    """Public DTO returned by the molecule API."""

    chembl_id: str = Field(..., description="ChEMBL compound identifier")
    pref_name: Optional[str] = Field(None, description="Preferred name from ChEMBL")
    canonical_smiles: Optional[str] = Field(None, description="Canonical SMILES string")
    inchi_key: Optional[str] = Field(None, description="Standard InChIKey")
    molecular_weight: Optional[float] = Field(None, description="Molecular weight (Da)")
