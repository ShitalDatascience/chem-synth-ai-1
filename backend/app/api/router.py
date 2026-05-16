from fastapi import APIRouter

from app.api.routes import chat, health, molecule, rag, report

api_router = APIRouter()


# =========================================================
# EXISTING ROUTES (Phase 1–3)
# =========================================================
api_router.include_router(health.router)
api_router.include_router(molecule.router)
api_router.include_router(rag.router)
api_router.include_router(report.router)
api_router.include_router(chat.router)