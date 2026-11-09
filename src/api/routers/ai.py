"""Engine & External API Settings FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter

from src.ai.external_client import test_external_connection
from src.ai.prompt_builder import build_transmission_disclosure
from src.api.schemas import AISettingsUpdateRequest
from src.api.state import get_container

router = APIRouter(prefix="/api/ai", tags=["Engine & External API Settings"])


@router.get("/settings")
def get_ai_settings():
    c = get_container()
    ctx = c.context_manager.get_snapshot()
    return {
        "config": c.ai_manager.config.to_safe_dict(),
        "external_disclosure": build_transmission_disclosure(
            ctx, include_sample_rows=c.ai_manager.config.include_sample_rows_in_external
        ),
    }


@router.post("/settings")
def update_ai_settings(payload: AISettingsUpdateRequest):
    c = get_container()
    cfg = c.ai_manager.update(payload.model_dump(exclude_none=True))
    ctx = c.context_manager.get_snapshot()
    return {
        "config": cfg.to_safe_dict(),
        "external_disclosure": build_transmission_disclosure(
            ctx, include_sample_rows=cfg.include_sample_rows_in_external
        ),
    }


@router.post("/test-external")
def check_external():
    c = get_container()
    return test_external_connection(c.ai_manager.config)
