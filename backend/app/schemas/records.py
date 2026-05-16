from pydantic import BaseModel


class MoleculeRecord(BaseModel):
    chembl_id: str
    pref_name: str | None = None
    canonical_smiles: str | None = None
    inchi_key: str | None = None
    molecular_weight: float | None = None

    def to_dto(self):
        from app.schemas.molecule import MoleculeIdentity

        return MoleculeIdentity(
            chembl_id=self.chembl_id,
            pref_name=self.pref_name,
            canonical_smiles=self.canonical_smiles,
            inchi_key=self.inchi_key,
            molecular_weight=self.molecular_weight,
        )