"""SQL Debugging Assistant FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import DebugAnalyzeRequest
from src.api.state import get_container
from src.debugger.assistant import analyze_and_debug_sql

router = APIRouter(prefix="/api/debug", tags=["Debugging Assistant"])


@router.post("/analyze")
def debug_sql(payload: DebugAnalyzeRequest):
    c = get_container()
    ctx = c.context_manager.get_snapshot()
    return analyze_and_debug_sql(
        payload.sql,
        ctx,
        dialect=payload.dialect or ctx.dialect,
        connector=c.context_manager.connector,
        captured_error=payload.captured_error,
        test_fixes=payload.test_fixes,
    )
