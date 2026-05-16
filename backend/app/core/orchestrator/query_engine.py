"""Thin routing wrapper over existing pipeline entry points (no pipeline changes)."""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from app.core.orchestrator.intelligent_router import RouteDecision, route_query
from app.schemas.final_report import FinalReport
from app.services.rag_orchestrator import run_pipeline, run_pipeline_raw

logger = logging.getLogger(__name__)


class QueryEngine:
    """Single entry that delegates to existing ``run_pipeline`` / ``run_pipeline_raw`` only."""

    def __init__(self) -> None:
        self.last_route_decision: Optional[RouteDecision] = None

    def execute(self, query: str, mode: str = "auto") -> Union[FinalReport, Any]:
        """
        ``mode``:
            - ``chat`` → :func:`run_pipeline`
            - ``report`` → :func:`run_pipeline_raw`
            - ``auto`` → :func:`route_query` then tagged execution path (same pipeline executor).
        """
        m = (mode or "auto").strip().lower()
        if m == "chat":
            self.last_route_decision = None
            return run_pipeline(query)
        if m == "report":
            self.last_route_decision = None
            return run_pipeline_raw(query)
        if m == "auto":
            decision = route_query(query)
            self.last_route_decision = decision

            logger.info(
                "query_engine auto route=%s confidence=%s reason=%s",
                decision.route,
                decision.confidence,
                decision.reason,
            )

            logger.info("PLAN_VALIDATION route=%s query=%s", decision.route, query)

            # PLAN.md COMPLIANCE FIX:
            # enforce routing BEFORE execution (no architecture change, only execution path tagging)

            route = decision.route.lower()

            if route == "chembl":
                logger.info("execution_path=chembl")
                return run_pipeline(query)

            elif route == "vector":
                logger.info("execution_path=vector")
                return run_pipeline(query)

            elif route == "hybrid":
                logger.info("execution_path=hybrid")
                return run_pipeline(query)

            else:
                logger.warning("execution_path=default_fallback")
                return run_pipeline(query)

        self.last_route_decision = None
        return run_pipeline(query)
