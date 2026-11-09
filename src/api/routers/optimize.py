"""Query Optimizer FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import OptimizeAnalyzeRequest
from src.api.state import get_container
from src.optimizer.engine import optimize_sql_query

router = APIRouter(prefix="/api/optimize", tags=["Query Optimizer"])


@router.post("/analyze")
def optimize_query(payload: OptimizeAnalyzeRequest):
    c = get_container()
    ctx = c.context_manager.get_snapshot()
    return optimize_sql_query(
        payload.sql,
        ctx,
        dialect=payload.dialect or ctx.dialect,
        connector=c.context_manager.connector,
        include_estimated_plan=payload.include_estimated_plan,
        allow_explain_analyze=payload.allow_explain_analyze,
        benchmark_candidate_sql=payload.benchmark_candidate_sql,
    )
