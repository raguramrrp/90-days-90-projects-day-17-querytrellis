"""Visual SQL Learning Academy & Custom Execution Tracer FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.academy.curriculum import list_lessons_summary
from src.academy.exercise_evaluator import evaluate_academy_exercise
from src.academy.stage_tracer import trace_custom_select_query, trace_lesson_execution
from src.api.schemas import CustomVisualizeRequest, ExerciseCheckRequest
from src.api.state import get_container
from src.dialects.sqlglot_engine import transpile_for_duckdb
from src.security.guardrails import evaluate_sql_safety

router = APIRouter(prefix="/api/academy", tags=["Visual SQL Academy"])


@router.get("/lessons")
def list_lessons():
    return {"lessons": list_lessons_summary()}


@router.get("/lessons/{lesson_id}")
def get_lesson_trace(lesson_id: str):
    res = trace_lesson_execution(lesson_id)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error_message", "Lesson not found."))
    return res


@router.post("/exercise/check")
def check_exercise(payload: ExerciseCheckRequest):
    res = evaluate_academy_exercise(payload.lesson_id, payload.user_sql)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("feedback", "Exercise error."))
    return res


@router.post("/visualize")
def visualize_custom_query(payload: CustomVisualizeRequest):
    c = get_container()
    ctx = c.context_manager.get_snapshot()
    safety = evaluate_sql_safety(payload.sql, dialect=ctx.dialect, allow_write_opt_in=False)
    if not safety.allowed or not safety.is_read_only:
        return {
            "success": False,
            "error_message": safety.error_message or "Visual execution requires a safe read-only SELECT query.",
            "stages": [],
        }
    duck_sql, notes, err = transpile_for_duckdb(payload.sql, ctx.dialect)
    if err:
        return {"success": False, "error_message": err, "stages": [], "notes": notes}
    db_path = c.context_manager.connector._duckdb_path if c.context_manager.connector._active_engine == "duckdb" else None
    if db_path is None:
        return {
            "success": False,
            "error_message": (
                "Custom visual stage execution traces queries against local DuckDB/uploaded datasets. "
                "Switch active database to Demo or an Uploaded Dataset, or use built-in Academy lessons."
            ),
            "stages": [],
        }
    out = trace_custom_select_query(duck_sql, db_path=db_path)
    out["notes"] = notes
    return out
