from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.orchestrator.query_engine import QueryEngine
from app.schemas.final_report import FinalReport
from app.services.report_service import assemble_report, build_final_report, get_report, list_report_ids

router = APIRouter()


class GenerateReportRequest(BaseModel):
    query: str


@router.get("/report/{report_id}", response_model=FinalReport)
def get_report_by_id(report_id: str) -> FinalReport:
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return build_final_report(report)


@router.get("/reports", response_model=list[str])
def list_reports() -> list[str]:
    return list_report_ids()


@router.post("/report", response_model=FinalReport)
def create_report(req: GenerateReportRequest) -> FinalReport:
    engine = QueryEngine()
    result = engine.execute(req.query, mode="report")
    report = assemble_report(result)
    return build_final_report(report)
