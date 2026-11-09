"""Unit tests for EXPLAIN JSON parsing, plan tree construction, and bottleneck analyzer."""
from __future__ import annotations

import pytest

from src.db.connection_manager import DatabaseCatalog
from src.explain.plan_analyzer import analyze_explain_plan
from src.explain.plan_parser import parse_explain_json


def test_parse_analyzed_plan_with_buffers_sort_and_nested_loop() -> None:
    raw = [
        {
            "Plan": {
                "Node Type": "Sort",
                "Startup Cost": 1200.5,
                "Total Cost": 1350.0,
                "Plan Rows": 100,
                "Plan Width": 40,
                "Actual Startup Time": 38.0,
                "Actual Total Time": 42.5,
                "Actual Rows": 5000,
                "Actual Loops": 1,
                "Sort Key": ["o.order_date DESC"],
                "Sort Method": "external merge",
                "Sort Space Used": 2048,
                "Sort Space Type": "Disk",
                "Shared Hit Blocks": 120,
                "Shared Read Blocks": 900,
                "Temp Written Blocks": 256,
                "Plans": [
                    {
                        "Node Type": "Seq Scan",
                        "Parent Relationship": "Outer",
                        "Relation Name": "orders",
                        "Alias": "o",
                        "Startup Cost": 0.0,
                        "Total Cost": 950.0,
                        "Plan Rows": 100,
                        "Plan Width": 40,
                        "Actual Startup Time": 0.05,
                        "Actual Total Time": 18.0,
                        "Actual Rows": 5000,
                        "Actual Loops": 1,
                        "Filter": "(customer_id = 420)",
                        "Rows Removed by Filter": 50000,
                        "Shared Hit Blocks": 120,
                        "Shared Read Blocks": 900,
                    }
                ],
            },
            "Planning Time": 0.312,
            "Execution Time": 43.105,
        }
    ]

    plan = parse_explain_json(raw)
    assert plan.analyzed is True
    assert plan.execution_time_ms == 43.105
    assert plan.planning_time_ms == 0.312
    assert len(plan.all_nodes) == 2
    assert plan.root.self_time_ms == pytest.approx(24.5, abs=0.01)
    assert plan.root.children[0].self_time_ms == pytest.approx(18.0, abs=0.01)
    assert plan.root.estimation_factor == 50.0

    tree_txt = plan.to_text_tree()
    assert "Sort" in tree_txt
    assert "Seq Scan on orders" in tree_txt
    assert "external merge" in tree_txt

    insights = analyze_explain_plan(plan)
    ids = {i.insight_id for i in insights}
    assert "EP001" in ids  # Selective seq scan on large table
    assert "EP002" in ids  # 50x estimation error
    assert "EP003" in ids  # Disk sort
    assert "EP005" in ids  # High buffer reads


def test_parse_estimate_only_plan_leaves_actuals_unavailable() -> None:
    raw = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "categories",
                "Startup Cost": 0.0,
                "Total Cost": 1.25,
                "Plan Rows": 25,
                "Plan Width": 64,
            }
        }
    ]
    plan = parse_explain_json(raw)
    assert plan.analyzed is False
    assert plan.execution_time_ms is None
    assert plan.root.actual_rows is None
    assert plan.root.actual_total_time is None
    assert "unavailable" in plan.to_text_tree().lower()


def test_small_table_seq_scan_noted_as_optimal(sample_catalog: DatabaseCatalog) -> None:
    raw = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "categories",
                "Startup Cost": 0.0,
                "Total Cost": 1.25,
                "Plan Rows": 25,
                "Actual Startup Time": 0.01,
                "Actual Total Time": 0.02,
                "Actual Rows": 25,
                "Actual Loops": 1,
            },
            "Execution Time": 0.05,
        }
    ]
    plan = parse_explain_json(raw)
    insights = analyze_explain_plan(plan, catalog=sample_catalog)
    assert any(i.insight_id == "EP001_INFO" and i.severity == "Info" for i in insights)


def test_malformed_explain_json_raises_clear_error() -> None:
    with pytest.raises(ValueError):
        parse_explain_json("{not valid json")
    with pytest.raises(ValueError):
        parse_explain_json([{"unexpected": 1}])
