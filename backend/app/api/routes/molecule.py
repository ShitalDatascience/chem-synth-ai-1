from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.schemas.molecule import MoleculeIdentity
from app.services.chembl_service import ChemblService

router = APIRouter()


@router.get("/molecule/{chembl_id}", response_model=MoleculeIdentity)
def get_molecule(chembl_id: str) -> MoleculeIdentity:
    svc = ChemblService()
    try:
        mol = svc.get_molecule_identity_by_chembl_id(chembl_id=chembl_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {type(e).__name__}") from e
    if mol is None:
        raise HTTPException(status_code=404, detail="Molecule not found")
    return mol


@router.get("/molecule/{chembl_id}/depict.png")
def depict_molecule_png(chembl_id: str) -> Response:
    svc = ChemblService()
    try:
        mol = svc.get_molecule_identity_by_chembl_id(chembl_id=chembl_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {type(e).__name__}") from e
    if mol is None or not mol.canonical_smiles:
        raise HTTPException(status_code=404, detail="Molecule or SMILES not found")

    try:
        from app.services.rdkit_service import depict_2d_png
        png_bytes = depict_2d_png(mol.canonical_smiles)
        return Response(content=png_bytes, media_type="image/png")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/molecule/{chembl_id}/depict.svg")
def depict_molecule_svg(chembl_id: str) -> Response:
    svc = ChemblService()
    try:
        mol = svc.get_molecule_identity_by_chembl_id(chembl_id=chembl_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {type(e).__name__}") from e
    if mol is None or not mol.canonical_smiles:
        raise HTTPException(status_code=404, detail="Molecule or SMILES not found")

    try:
        from app.services.rdkit_service import depict_2d_svg
        svg = depict_2d_svg(mol.canonical_smiles)
        return Response(content=svg, media_type="image/svg+xml")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/molecule/inchikey/{inchi_key}", response_model=MoleculeIdentity)
def get_molecule_by_inchi_key(inchi_key: str) -> MoleculeIdentity:
    svc = ChemblService()
    try:
        mol = svc.get_molecule_identity_by_inchi_key(inchi_key=inchi_key)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {type(e).__name__}") from e
    if mol is None:
        raise HTTPException(status_code=404, detail="Molecule not found")
    return mol
