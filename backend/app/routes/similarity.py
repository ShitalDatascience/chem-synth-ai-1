from fastapi import APIRouter

from app.services.chembl_service import ChemblService
from app.services.similarity.similarity_service import SimilarityService

router = APIRouter(prefix="/similarity", tags=["Similarity"])

config = {
    "host": "localhost",
    "database": "chembl",
    "user": "shitalkale",
    "password": ""
}

chembl = ChemblService(config)
chembl.connect()

service = SimilarityService(chembl)


@router.get("/build")
def build():
    # small test batch (you can expand later)
    sample_ids = ["CHEMBL941"]
    service.build_index(sample_ids)
    return {"status": "index built"}


@router.get("/{chembl_id}")
def similar(chembl_id: str):
    return service.find_similar(chembl_id)
