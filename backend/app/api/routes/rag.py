from fastapi import APIRouter, Query
from app.services.resolution.molecule_resolver import MoleculeResolver
from app.services.evidence.chembl_evidence_fetcher import ChemblEvidenceFetcher
from app.services.rag.evidence_bundle import EvidenceBundleBuilder

router = APIRouter()


@router.get("/rag/molecule")
def get_molecule_rag(name: str = Query(..., description="Molecule name")):

    # STEP 1: Resolve molecule
    results = MoleculeResolver.resolve_by_name(name)

    if not results:
        return {
            "status": "not_found",
            "message": f"No molecule found for '{name}'"
        }

    molecule = results[0]
    chembl_id = molecule["chembl_id"]

    # STEP 2: Fetch evidence
    evidence = ChemblEvidenceFetcher.fetch_by_chembl_id(chembl_id)

    # STEP 3: Build RAG bundle
    bundle = EvidenceBundleBuilder.build(chembl_id, evidence)

    return bundle
