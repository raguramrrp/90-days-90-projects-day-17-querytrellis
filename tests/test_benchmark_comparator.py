"""Unit tests for multi-run benchmark statistics and before/after query comparison."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.benchmark.comparator import QuerySnapshot, compare_queries
from src.benchmark.runner import (
    BenchmarkIteration,
    BenchmarkSummary,
    compute_timing_stats,
    run_query_benchmark,
)
from src.db.safe_executor import ExplainExecutionResult
from src.explain.plan_parser import parse_explain_json
from src.sql_analysis.antipattern_detector import AntiPatternFinding
from src.sql_analysis.parser_validator import validate_read_only_sql


def test_compute_timing_stats_values() -> None:
    stats = compute_timing_stats([10.0, 20.0, 30.0, 40.0, 100.0])
    assert stats["min"] == 10.0
    assert stats["max"] == 100.0
    assert stats["mean"] == 40.0
    assert stats["median"] == 30.0
    assert stats["p95"] == 100.0
    assert stats["stdev"] > 0.0


def test_run_query_benchmark_rejects_unsafe_and_handles_interruption() -> None:
    bad = run_query_benchmark(None, "DROP TABLE orders")  # type: ignore[arg-type]
    assert bad.success is False
    assert "Blocked" in bad.error_message

    val = validate_read_only_sql("SELECT order_id FROM orders WHERE customer_id = 1")
    plan_ok = [
        {
            "Plan": {
                "Node Type": "Index Scan",
                "Relation Name": "orders",
                "Index Name": "idx_orders_customer_id",
                "Startup Cost": 0.29,
                "Total Cost": 8.5,
                "Plan Rows": 5,
                "Actual Startup Time": 0.02,
                "Actual Total Time": 0.04,
                "Actual Rows": 5,
                "Actual Loops": 1,
                "Shared Hit Blocks": 4,
                "Shared Read Blocks": 0,
            },
            "Planning Time": 0.1,
            "Execution Time": 0.08,
        }
    ]
    responses = [
        ExplainExecutionResult(True, val, True, True, plan_ok, 1.2),
        ExplainExecutionResult(True, val, True, True, plan_ok, 1.1),
        ExplainExecutionResult(False, val, True, True, None, 5000.0, "Query timed out"),
    ]
    with patch("src.benchmark.runner.run_explain_plan", side_effect=responses):
        res = run_query_benchmark(None, "SELECT order_id FROM orders WHERE customer_id = 1", repeat_count=3)  # type: ignore[arg-type]
    assert res.success is True
    assert res.interrupted is True
    assert res.repeat_count == 2
    assert res.pg_exec_median_ms == pytest.approx(0.08, abs=0.001)


def test_compare_queries_improved_regressed_and_row_mismatch() -> None:
    plan_a = parse_explain_json(
        [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Total Cost": 1500.0,
                    "Plan Rows": 100,
                    "Actual Startup Time": 1.0,
                    "Actual Total Time": 50.0,
                    "Actual Rows": 42,
                    "Actual Loops": 1,
                },
                "Execution Time": 52.0,
            }
        ]
    )
    plan_b = parse_explain_json(
        [
            {
                "Plan": {
                    "Node Type": "Index Scan",
                    "Relation Name": "orders",
                    "Index Name": "idx_orders_customer_id",
                    "Total Cost": 12.0,
                    "Plan Rows": 42,
                    "Actual Startup Time": 0.02,
                    "Actual Total Time": 0.4,
                    "Actual Rows": 42,
                    "Actual Loops": 1,
                },
                "Execution Time": 0.5,
            }
        ]
    )

    ap_a = [
        AntiPatternFinding(
            "AP001", "Wildcard Projection (SELECT *)", "Medium", "SELECT *",
            "...", "...", "...", "...", "High", "AST"
        )
    ]

    snap_a = QuerySnapshot("Baseline", "SELECT * FROM orders", plan=plan_a, antipatterns=ap_a)
    snap_b = QuerySnapshot("Optimized", "SELECT order_id FROM orders", plan=plan_b, antipatterns=[])

    cmp = compare_queries(snap_a, snap_b)
    assert cmp.verdict == "Improved"
    assert cmp.row_count_matches is True
    assert cmp.pct_change is not None and cmp.pct_change < -90.0
    assert "idx_orders_customer_id" in cmp.indexes_added
    assert "Wildcard Projection (SELECT *)" in cmp.resolved_antipatterns

    # Regression check
    cmp_reg = compare_queries(snap_b, snap_a)
    assert cmp_reg.verdict == "Regressed"

    # Row mismatch check prevents falsely claiming optimization succeeded!
    plan_mismatch = parse_explain_json(
        [
            {
                "Plan": {
                    "Node Type": "Index Scan",
                    "Relation Name": "orders",
                    "Total Cost": 5.0,
                    "Plan Rows": 10,
                    "Actual Startup Time": 0.01,
                    "Actual Total Time": 0.1,
                    "Actual Rows": 10,
                    "Actual Loops": 1,
                },
                "Execution Time": 0.2,
            }
        ]
    )
    cmp_bad = compare_queries(snap_a, QuerySnapshot("Wrong", "SELECT order_id FROM orders LIMIT 10", plan=plan_mismatch))
    assert cmp_bad.verdict == "Row Count Mismatch"
    assert cmp_bad.row_count_matches is False
