"""Live PostgreSQL integration tests for QueryTrellis.

Runs against the configured PostgreSQL instance (from .env / environment variables).
Skips cleanly with an explicit reason if no live sample database is reachable.
"""
from __future__ import annotations

import os

import pytest

from src.benchmark.comparator import QuerySnapshot, compare_queries
from src.benchmark.runner import run_query_benchmark
from src.config.settings import load_settings
from src.db.connection_manager import ConnectionManager
from src.db.safe_executor import execute_safe_query
from src.services.workbench_service import analyze_query_end_to_end

pytestmark = pytest.mark.integration


def _get_live_manager() -> ConnectionManager:
    settings = load_settings()
    cfg = settings.connection
    if os.getenv("QT_TEST_PG_HOST"):
        cfg.host = os.environ["QT_TEST_PG_HOST"]
    if os.getenv("QT_TEST_PG_PORT"):
        cfg.port = int(os.environ["QT_TEST_PG_PORT"])
    if os.getenv("QT_TEST_PG_DB"):
        cfg.database = os.environ["QT_TEST_PG_DB"]
    if os.getenv("QT_TEST_PG_USER"):
        cfg.username = os.environ["QT_TEST_PG_USER"]
    if "QT_TEST_PG_PASSWORD" in os.environ:
        cfg.password = os.environ["QT_TEST_PG_PASSWORD"]

    mgr = ConnectionManager(cfg)
    status = mgr.connect(cfg)
    if not status.connected:
        pytest.skip(f"Live PostgreSQL not reachable for integration test: {status.error_message}")
    return mgr


def test_live_catalog_and_safe_execution_and_benchmark() -> None:
    mgr = _get_live_manager()
    try:
        catalog = mgr.fetch_catalog()
        table_names = {t.table_name for t in catalog.tables}
        expected_tables = {"customers", "products", "categories", "orders", "order_items", "payments", "shipments", "reviews"}
        if not expected_tables.issubset(table_names):
            pytest.skip("Sample e-commerce tables not yet seeded in target PostgreSQL database.")

        # Safe query execution with max_rows cap
        exec_res = execute_safe_query(
            mgr.get_connection(),
            "SELECT order_id, customer_id, status FROM orders ORDER BY order_id",
            timeout_ms=5000,
            max_rows=25,
        )
        assert exec_res.success is True
        assert exec_res.rows_returned == 25
        assert exec_res.was_truncated is True

        # Reject write operation before execution
        blocked = execute_safe_query(mgr.get_connection(), "DELETE FROM orders WHERE order_id = 1")
        assert blocked.success is False

        # End-to-end analysis with live EXPLAIN (ANALYZE, BUFFERS)
        bundle = analyze_query_end_to_end(
            "SELECT order_id, customer_id, total_amount FROM orders WHERE customer_id = 420",
            conn_manager=mgr,
            persist=False,
        )
        assert bundle.parsed_plan is not None
        assert bundle.parsed_plan.analyzed is True
        assert bundle.parsed_plan.execution_time_ms is not None
        assert any("customer_id" in r.columns for r in bundle.index_recommendations)

        # Live benchmark & comparison
        q_slow = "SELECT * FROM customers WHERE LOWER(email) = 'customer125@example.com'"
        q_fast = "SELECT customer_id, email FROM customers WHERE email = 'customer125@example.com'"
        b1 = run_query_benchmark(mgr.get_connection(), q_slow, label="Slow", repeat_count=3, include_warmup=True)
        b2 = run_query_benchmark(mgr.get_connection(), q_fast, label="Fast", repeat_count=3, include_warmup=True)
        assert b1.success and b2.success

        a1 = analyze_query_end_to_end(q_slow, conn_manager=mgr, persist=False)
        a2 = analyze_query_end_to_end(q_fast, conn_manager=mgr, persist=False)
        cmp = compare_queries(
            QuerySnapshot("Slow", q_slow, plan=a1.parsed_plan, benchmark=b1, antipatterns=a1.antipatterns),
            QuerySnapshot("Fast", q_fast, plan=a2.parsed_plan, benchmark=b2, antipatterns=a2.antipatterns),
        )
        assert cmp.row_count_matches is True
        assert cmp.verdict == "Improved"
    finally:
        mgr.disconnect()
