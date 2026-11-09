"""Unit tests for the QueryTrellis end-to-end workbench orchestrator and sample queries."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.db.connection_manager import DatabaseCatalog
from src.db.metadata_store import MetadataStore
from src.db.safe_executor import ExplainExecutionResult, QueryExecutionResult
from src.services.workbench_service import analyze_query_end_to_end, execute_and_record_query
from src.sql_analysis.parser_validator import validate_read_only_sql
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def test_all_sample_queries_pass_read_only_validation() -> None:
    assert len(SAMPLE_QUERIES) >= 8
    for sample in SAMPLE_QUERIES:
        res = validate_read_only_sql(sample.sql)
        assert res.is_valid and res.is_read_only, f"Sample {sample.key} failed validation: {res.error_message}"
        if sample.suggested_optimization:
            opt_res = validate_read_only_sql(sample.suggested_optimization)
            assert opt_res.is_valid and opt_res.is_read_only


def test_analyze_query_end_to_end_offline_and_persisted(temp_store: MetadataStore) -> None:
    bundle = analyze_query_end_to_end(
        "SELECT * FROM orders WHERE LOWER(status) = 'delivered'",
        conn_manager=None,
        metadata_store=temp_store,
        persist=True,
    )
    assert bundle.validation.is_read_only is True
    assert bundle.parsed_plan is None
    assert len(bundle.antipatterns) >= 2
    assert bundle.analysis_id is not None

    saved = temp_store.get_analysis(bundle.analysis_id)
    assert saved is not None
    assert saved["execution_mode"] == "static_only"


def test_analyze_query_end_to_end_rejects_write_and_records(temp_store: MetadataStore) -> None:
    bundle = analyze_query_end_to_end(
        "DROP TABLE orders",
        conn_manager=None,
        metadata_store=temp_store,
        persist=True,
    )
    assert bundle.validation.is_read_only is False
    assert "Blocked" in bundle.error_message
    rows = temp_store.list_analyses(status_filter="rejected")
    assert len(rows) == 1


def test_analyze_and_execute_with_mocked_connection_manager(
    temp_store: MetadataStore, sample_catalog: DatabaseCatalog
) -> None:
    mgr = MagicMock()
    mgr.is_connected = True
    mgr.status.current_database = "querytrellis_sample"
    mgr.fetch_catalog.return_value = sample_catalog
    mgr.get_connection.return_value = MagicMock()

    val = validate_read_only_sql("SELECT order_id FROM orders WHERE customer_id = 420")
    raw_plan = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Startup Cost": 0.0,
                "Total Cost": 1200.0,
                "Plan Rows": 10,
                "Actual Startup Time": 0.1,
                "Actual Total Time": 12.0,
                "Actual Rows": 5,
                "Actual Loops": 1,
                "Filter": "(customer_id = 420)",
                "Rows Removed by Filter": 54995,
            },
            "Planning Time": 0.2,
            "Execution Time": 12.3,
        }
    ]
    with patch(
        "src.services.workbench_service.run_explain_plan",
        return_value=ExplainExecutionResult(True, val, True, True, raw_plan, 13.0),
    ):
        bundle = analyze_query_end_to_end(
            "SELECT order_id FROM orders WHERE customer_id = 420",
            conn_manager=mgr,
            metadata_store=temp_store,
            persist=True,
        )
    assert bundle.parsed_plan is not None
    assert bundle.parsed_plan.execution_time_ms == 12.3
    assert any("orders(customer_id)" in r.suggested_sql for r in bundle.index_recommendations)

    with patch(
        "src.services.workbench_service.execute_safe_query",
        return_value=QueryExecutionResult(True, val, ["order_id"], [(1,)], 1, False, 500, 3.2),
    ):
        exec_res = execute_and_record_query(
            "SELECT order_id FROM orders WHERE customer_id = 420",
            conn_manager=mgr,
            metadata_store=temp_store,
        )
    assert exec_res.success is True
    assert exec_res.rows_returned == 1
