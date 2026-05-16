from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    ok: bool


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return {"ok": True}

