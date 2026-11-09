"""Tests for Debugging Assistant, 3-Tier Query Optimizer, 21-Lesson Visual SQL Academy, AI Consent, and FastAPI endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.academy.curriculum import ACADEMY_LESSONS
from src.academy.exercise_evaluator import evaluate_academy_exercise
from src.academy.stage_tracer import trace_custom_select_query, trace_lesson_execution
from src.ai.external_client import generate_with_external_ai
from src.ai.provider_base import AIProviderConfig
from src.api.main import app
from src.context.context_manager import ActiveContextManager
from src.debugger.assistant import analyze_and_debug_sql
from src.optimizer.engine import optimize_sql_query


def test_debugging_assistant_detects_errors_warnings_and_verifies_candidate_fixes():
    mgr = ActiveContextManager()
    ctx = mgr.get_snapshot()

    # 1. Missing column typo + NULL equality trap
    bad_sql = "SELECT e.employee_id, e.emial FROM employees e WHERE e.hire_date = NULL;"
    rep = analyze_and_debug_sql(bad_sql, ctx, dialect="postgresql", connector=mgr.connector)
    assert rep["has_errors"] is True
    codes = {d["code"] for d in rep["diagnostics"]}
    assert "DBG_MISSING_COLUMN" in codes
    assert "DBG_LOGIC_NULL" in codes
    assert len(rep["fix_candidates"]) >= 1
    assert any(c["test_passed"] is True for c in rep["fix_candidates"])

    # 2. Ambiguous column & missing JOIN ON condition -> FK-guided fix
    join_bad = "SELECT department_id, department_name FROM employees e JOIN departments d;"
    jrep = analyze_and_debug_sql(join_bad, ctx, dialect="postgresql", connector=mgr.connector)
    jcodes = {d["code"] for d in jrep["diagnostics"]}
    assert "DBG_JOIN_MISSING_ON" in jcodes
    assert "DBG_AMBIGUOUS_COLUMN" in jcodes
    assert any(c["test_passed"] is True for c in jrep["fix_candidates"])

    # 3. Missing GROUP BY column
    grp_bad = "SELECT department_id, COUNT(employee_id) AS cnt FROM employees;"
    grep = analyze_and_debug_sql(grp_bad, ctx, dialect="postgresql", connector=mgr.connector)
    gcodes = {d["code"] for d in grep["diagnostics"]}
    assert "DBG_GROUP_BY_MISMATCH" in gcodes
    assert any(c["test_passed"] is True for c in grep["fix_candidates"])

    # 4. Datatype comparison mismatch
    dt_bad = "SELECT employee_id FROM employees WHERE base_salary = 'not_a_number';"
    drep = analyze_and_debug_sql(dt_bad, ctx, dialect="postgresql", connector=mgr.connector)
    assert any(d["code"] == "DBG_DATATYPE" for d in drep["diagnostics"])


def test_optimizer_enforces_three_tier_separation_without_fabricating_timings():
    mgr = ActiveContextManager()
    ctx = mgr.get_snapshot()
    slow_sql = "SELECT * FROM orders WHERE EXTRACT(YEAR FROM order_date) = 2026 ORDER BY order_date DESC;"

    # Opt-in EXPLAIN ANALYZE disabled -> measured_performance['executed'] MUST be False
    static_and_est = optimize_sql_query(
        slow_sql,
        ctx,
        dialect="postgresql",
        connector=mgr.connector,
        include_estimated_plan=True,
        allow_explain_analyze=False,
    )
    assert static_and_est["success"] is True
    assert len(static_and_est["static_suggestions"]["antipatterns"]) >= 1
    assert len(static_and_est["static_suggestions"]["rewrite_alternatives"]) >= 1
    assert static_and_est["estimated_plan"]["success"] is True
    assert static_and_est["estimated_plan"]["plan_kind"] == "estimated_plan"
    assert static_and_est["measured_performance"]["executed"] is False

    # Opt-in EXPLAIN ANALYZE enabled -> real measured duration & candidate A/B comparison
    rw = static_and_est["static_suggestions"]["rewrite_alternatives"][0]["rewritten_sql"]
    measured = optimize_sql_query(
        slow_sql,
        ctx,
        dialect="postgresql",
        connector=mgr.connector,
        include_estimated_plan=True,
        allow_explain_analyze=True,
        benchmark_candidate_sql=rw,
    )
    assert measured["measured_performance"]["executed"] is True
    assert measured["measured_performance"]["original"]["duration_ms"] >= 0
    assert measured["measured_performance"]["candidate"]["row_count_matches"] is True


def test_visual_sql_academy_all_21_lessons_trace_and_evaluate():
    assert len(ACADEMY_LESSONS) == 21
    for lesson in ACADEMY_LESSONS:
        trace = trace_lesson_execution(lesson.lesson_id)
        assert trace["success"] is True, f"Trace failed for {lesson.lesson_id}: {trace}"
        assert len(trace["stages"]) >= 2, f"Expected >=2 stages for {lesson.lesson_id}"

        passed = evaluate_academy_exercise(lesson.lesson_id, lesson.exercise.solution_sql)
        assert passed["success"] and passed["passed"], f"Official solution failed for {lesson.lesson_id}: {passed['feedback']}"

        failed = evaluate_academy_exercise(lesson.lesson_id, "SELECT 1 AS wrong_col;")
        assert not failed["passed"]


def test_custom_select_tracer_captures_kept_and_excluded_rows():
    res = trace_custom_select_query(
        "SELECT emp_id, emp_name, salary FROM staff WHERE salary >= 85000 ORDER BY salary DESC LIMIT 3;"
    )
    assert res["success"] is True
    keys = [s["stage_key"] for s in res["stages"]]
    assert "FROM_JOIN" in keys
    assert "WHERE" in keys
    assert "ORDER_BY" in keys
    assert "FINAL" in keys
    where_stage = next(s for s in res["stages"] if s["stage_key"] == "WHERE")
    statuses = {m["status"] for m in where_stage["row_meta"]}
    assert statuses == {"kept", "excluded"}


def test_external_ai_requires_explicit_consent_and_hides_api_key():
    cfg = AIProviderConfig(
        active_provider="external",
        external_provider="openai",
        external_api_key="sk-secret-key-should-never-leak-1234",
        external_data_consent=False,
    )
    safe = cfg.to_safe_dict()
    assert "sk-secret" not in str(safe)
    assert safe["external_api_key_configured"] is True

    blocked = generate_with_external_ai([{"role": "user", "content": "hi"}], cfg)
    assert not blocked.success
    assert "consent" in blocked.error_message.lower()


def test_fastapi_end_to_end_routes_and_privacy():
    client = TestClient(app)

    r_health = client.get("/api/health")
    assert r_health.status_code == 200 and r_health.json()["status"] == "ok"

    r_ctx = client.get("/api/context")
    assert r_ctx.status_code == 200
    assert len(r_ctx.json()["tables"]) >= 7

    # Clarification then SQL generation
    r_ambig = client.post("/api/nl2sql/generate", json={"request": "Show the top 10 performing employees."})
    assert r_ambig.status_code == 200
    assert r_ambig.json()["status"] == "clarification_required"

    r_gen = client.post(
        "/api/nl2sql/generate",
        json={
            "request": "Show the top 10 performing employees.",
            "dialect": "mysql",
            "clarification_answer": "Total revenue generated",
            "force_provider": "deterministic",
        },
    )
    assert r_gen.status_code == 200
    gen_data = r_gen.json()
    assert gen_data["status"] == "generated" and gen_data["schema_verified"] is True

    r_exec = client.post(
        "/api/sql/execute",
        json={"sql": gen_data["sql"], "dialect": "mysql", "max_rows": 10},
    )
    assert r_exec.status_code == 200 and r_exec.json()["success"] is True

    r_lessons = client.get("/api/academy/lessons")
    assert r_lessons.status_code == 200 and len(r_lessons.json()["lessons"]) == 21

    r_ai = client.post(
        "/api/ai/settings",
        json={"external_api_key": "sk-testsecret-999999", "external_data_consent": False},
    )
    assert r_ai.status_code == 200
    assert "sk-testsecret" not in r_ai.text
