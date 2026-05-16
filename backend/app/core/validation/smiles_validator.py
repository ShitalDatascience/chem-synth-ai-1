import re
from rdkit import Chem

class SmilesValidator:
    """
    Validates SMILES strings using RDKit + lightweight heuristics
    """

    @staticmethod
    def is_valid_smiles(smiles: str) -> bool:
        if not smiles or not isinstance(smiles, str):
            return False

        # basic heuristic check
        allowed = re.compile(r'^[A-Za-z0-9@+\-\[\]\(\)=#%\\/\.]+$')
        if not allowed.match(smiles):
            return False

        # RDKit validation (final gate)
        mol = Chem.MolFromSmiles(smiles)
        return mol is not None
