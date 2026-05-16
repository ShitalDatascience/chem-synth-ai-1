import re

class MoleculeValidator:
    """
    Central validation layer for molecule-related inputs.
    Keeps service layer clean.
    """

    @staticmethod
    def validate_chembl_id(chembl_id: str) -> bool:
        """
        Validates ChEMBL ID format (basic rule).
        Example valid: CHEMBL25, CHEMBL12345
        """
        if not chembl_id:
            return False

        return bool(re.match(r"^CHEMBL\d+$", chembl_id))


    @staticmethod
    def validate_inchikey(inchi_key: str) -> bool:
        """
        InChIKey format: 27 characters with 2 hyphens (basic check)
        Example: BSYNRYMUTXBXSQ-UHFFFAOYSA-N
        """
        if not inchi_key:
            return False

        return bool(re.match(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$", inchi_key))


    @staticmethod
    def sanitize_smiles(smiles: str) -> str:
        """
        Basic cleanup (optional safety layer)
        """
        if not smiles:
            return ""
        return smiles.strip()