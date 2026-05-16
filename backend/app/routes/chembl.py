from fastapi import APIRouter

from app.services.chembl_service import ChemblService

# 🔹 CREATE ROUTER (THIS WAS MISSING)
router = APIRouter(prefix="/chembl", tags=["ChEMBL"])

# 🔹 DB CONFIG
config = {
    "host": "localhost",
    "database": "chembl",
    "user": "shitalkale",
    "password": ""
}

service = ChemblService(config)
service.connect()


# =====================================================
# ENDPOINTS
# =====================================================

@router.get("/molecule/{chembl_id}")
def get_molecule(chembl_id: str):
    return service.get_activities_by_mol(chembl_id, limit=10)


@router.get("/summary/{chembl_id}")
def get_summary(chembl_id: str):
    return service.get_molecule_summary(chembl_id, limit=50)


@router.get("/fingerprint/{chembl_id}")
def get_fingerprint(chembl_id: str):
    return service.get_molecule_fingerprint(chembl_id)