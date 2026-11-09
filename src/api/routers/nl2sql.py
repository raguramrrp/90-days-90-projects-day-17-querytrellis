"""Natural Language to SQL Generation & Explanation FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import NLGenerateRequest
from src.api.state import get_container
from src.nl2sql.generator import generate_sql_from_nl

router = APIRouter(prefix="/api/nl2sql", tags=["Query Studio NL2SQL"])


@router.post("/generate")
def generate_query(payload: NLGenerateRequest):
    c = get_container()
    ctx = c.context_manager.get_snapshot()
    return generate_sql_from_nl(
        payload.request,
        ctx,
        c.ai_manager.config,
        dialect=payload.dialect or ctx.dialect,
        clarification_answer=payload.clarification_answer,
        force_provider=payload.force_provider,
    )
