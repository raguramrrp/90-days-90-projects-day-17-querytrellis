"""Unit tests for HTML, JSON, and CSV report generation and secret scrubbing."""
from __future__ import annotations

import json

from src.advisor.index_recommender import IndexRecommendation
from src.benchmark.runner import BenchmarkIteration, BenchmarkSummary
from src.config.settings import ConnectionConfig
from src.explain.plan_parser import parse_explain_json
from src.reporting.report_generator import (
    build_benchmark_csv,
    build_html_report,
    build_json_report,
    build_plan_nodes_csv,
)
from src.sql_analysis.antipattern_detector import AntiPatternFinding


def test_reports_never_expose_passwords_and_export_cleanly() -> None:
    secret_pw = "SuperSecretPassword987!"
    cfg = ConnectionConfig(
        host="localhost",
        port=5432,
        database="querytrellis_sample",
        username="postgres",
        password=secret_pw,
    )
    plan = parse_explain_json(
        [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Startup Cost": 0.0,
                    "Total Cost": 200.0,
                    "Plan Rows": 100,
                    "Actual Startup Time": 0.1,
                    "Actual Total Time": 5.0,
                    "Actual Rows": 50,
                    "Actual Loops": 1,
                },
                "Planning Time": 0.2,
                "Execution Time": 5.2,
            }
        ]
    )
    bench = BenchmarkSummary(
        success=True,
        label="Test Bench",
        sql_text="SELECT order_id FROM orders WHERE customer_id = 10",
        sql_hash="abc123",
        repeat_count=2,
        warmup_used=False,
        min_ms=4.0,
        max_ms=6.0,
        mean_ms=5.0,
        median_ms=5.0,
        p95_ms=6.0,
        stdev_ms=1.414,
        pg_exec_min_ms=3.5,
        pg_exec_max_ms=5.5,
        pg_exec_mean_ms=4.5,
        pg_exec_median_ms=4.5,
        iterations=[
            BenchmarkIteration(1, False, 4.0, 0.2, 3.5, 50, 10, 0),
            BenchmarkIteration(2, False, 6.0, 0.2, 5.5, 50, 10, 0),
        ],
    )
    ap = [
        AntiPatternFinding("AP001", "Wildcard Projection", "Medium", "SELECT *", "exp", "imp", "ok", "fix", "High", "AST")
    ]
    rec = [
        IndexRecommendation(
            "IDX001", "orders", ["customer_id"], [], None, "Single-Column B-tree",
            "CREATE INDEX idx_orders_customer_id ON orders(customer_id);",
            "customer_id = 10", "faster lookup", "none", "write cost", "low selectivity", "High", ["AST"]
        )
    ]

    html_out = build_html_report(
        title="Security Audit Report",
        sql_text="SELECT order_id FROM orders WHERE customer_id = 10",
        connection_info=cfg,
        server_version="PostgreSQL 18.6",
        plan=plan,
        antipatterns=ap,
        index_recommendations=rec,
        benchmark=bench,
    )
    json_out = build_json_report(
        title="Security Audit Report",
        sql_text="SELECT order_id FROM orders WHERE customer_id = 10",
        connection_info=cfg,
        server_version="PostgreSQL 18.6",
        plan=plan,
        antipatterns=ap,
        index_recommendations=rec,
        benchmark=bench,
    )
    bench_csv = build_benchmark_csv(bench)
    nodes_csv = build_plan_nodes_csv(plan)

    assert secret_pw not in html_out
    assert secret_pw not in json_out
    assert "CREATE INDEX idx_orders_customer_id" in html_out
    parsed_json = json.loads(json_out)
    assert parsed_json["database_info"]["database"] == "querytrellis_sample"
    assert "password" not in parsed_json["database_info"]
    assert "client_wall_ms" in bench_csv
    assert "Seq Scan" in nodes_csv
