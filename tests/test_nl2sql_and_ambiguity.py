"""Tests for Schema-grounded NL2SQL, ambiguity clarification, missing-schema refusal, and dialect transpilation."""
from __future__ import annotations

import pytest

from src.ai.provider_base import AIProviderConfig
from src.context.context_manager import ActiveContextManager
from src.dialects.sqlglot_engine import SUPPORTED_DIALECTS
from src.nl2sql.explainer import explain_sql_query, verify_sql_against_schema
from src.nl2sql.generator import generate_sql_from_nl


def _demo_setup():
    mgr = ActiveContextManager()
    ctx = mgr.get_snapshot()
    cfg = AIProviderConfig(active_provider="deterministic")
    return mgr, ctx, cfg


def test_ambiguous_performance_prompt_requests_clarification_before_sql():
    mgr, ctx, cfg = _demo_setup()
    res = generate_sql_from_nl("Show the top 10 performing employees.", ctx, cfg)
    assert res["status"] == "clarification_required"
    assert "performance metric" in res["question"].lower()
    assert len(res["interpretations"]) >= 3

    # Once clarified, returns verified executable SQL across all 4 dialects
    for dialect in SUPPORTED_DIALECTS:
        clar = generate_sql_from_nl(
            "Show the top 10 performing employees.",
            ctx,
            cfg,
            dialect=dialect,
            clarification_answer="Total revenue generated",
        )
        assert clar["status"] == "generated"
        assert clar["schema_verified"] is True
        exec_res = mgr.connector.execute_sql(clar["sql"], dialect=dialect, max_rows=20)
        assert exec_res.success, f"Dialect {dialect} execution failed: {exec_res.error_message}"
        assert exec_res.rows_returned > 0


def test_missing_schema_entities_are_blocked_never_invented():
    _mgr, ctx, cfg = _demo_setup()
    res = generate_sql_from_nl(
        "Show average flight delay for hospital patients and invoices.",
        ctx,
        cfg,
    )
    assert res["status"] == "missing_schema"
    assert set(res["missing_entities"]).intersection({"flight", "patients", "hospital", "invoices"})
    assert "sql" not in res


@pytest.mark.parametrize(
    "prompt,clarification",
    [
        ("Calculate monthly revenue for each region.", None),
        ("Find customers who purchased more than three times.", None),
        ("Compare this month's sales with the previous month.", "Compare the latest two months of available data"),
        ("Identify products with declining sales.", "Latest month dropped compared to previous month"),
        ("Find employees whose performance is above the department average.", "Total revenue generated"),
        ("Calculate a running total of monthly revenue.", None),
        ("Find duplicate customer records.", "Duplicate email address"),
    ],
)
def test_all_core_analytics_prompts_generate_verified_executable_sql(prompt: str, clarification: str | None):
    mgr, ctx, cfg = _demo_setup()
    if clarification is not None:
        amb = generate_sql_from_nl(prompt, ctx, cfg)
        assert amb["status"] == "clarification_required", f"Expected ambiguity check for '{prompt}'"
    first = generate_sql_from_nl(prompt, ctx, cfg, clarification_answer=clarification)
    assert first["status"] == "generated", f"Unexpected status for '{prompt}': {first}"
    assert first["schema_verified"] is True
    assert first["illustrative_structure"]["is_illustrative_only"] is True
    assert len(first["clause_breakdown"]) >= 1

    exec_res = mgr.connector.execute_sql(first["sql"], dialect="postgresql", max_rows=50)
    assert exec_res.success, f"Generated SQL failed execution for '{prompt}': {exec_res.error_message}\nSQL:\n{first['sql']}"


def test_schema_verification_rejects_hallucinated_identifiers():
    _mgr, ctx, _cfg = _demo_setup()
    bad_ver = verify_sql_against_schema(
        "SELECT astronaut_name FROM spaceships;",
        ctx,
        "postgresql",
    )
    assert not bad_ver.schema_verified
    assert "spaceships" in bad_ver.unknown_tables

    expl = explain_sql_query(
        "SELECT employee_id, first_name FROM employees ORDER BY base_salary DESC LIMIT 5;",
        context=ctx,
        dialect="postgresql",
    )
    assert expl["schema_verified"] is True
    assert expl["illustrative_structure"]["is_illustrative_only"] is True
