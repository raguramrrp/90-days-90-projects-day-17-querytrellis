"""Unit tests for safe read-only query executor using mocked psycopg connections."""
from __future__ import annotations

from unittest.mock import MagicMock

import psycopg

from src.db.safe_executor import execute_safe_query, run_explain_plan


def _mock_conn(rows: list[tuple] | None = None, cols: list[str] | None = None, explain_payload=None):
    conn = MagicMock()
    conn.info.transaction_status = psycopg.pq.TransactionStatus.IDLE

    tx_cm = MagicMock()
    tx_cm.__enter__.return_value = None
    tx_cm.__exit__.return_value = False
    conn.transaction.return_value = tx_cm

    guard_cur = MagicMock()
    server_cur = MagicMock()
    if cols:
        server_cur.description = [MagicMock(name=c) for c in cols]
        for desc, cname in zip(server_cur.description, cols):
            desc.name = cname
    else:
        server_cur.description = []
    server_cur.fetchmany.return_value = rows or []
    guard_cur.fetchone.return_value = [explain_payload] if explain_payload is not None else None

    def _cursor_factory(*args, **kwargs):
        cm = MagicMock()
        if "name" in kwargs:
            cm.__enter__.return_value = server_cur
        else:
            cm.__enter__.return_value = guard_cur
        cm.__exit__.return_value = False
        return cm

    conn.cursor.side_effect = _cursor_factory
    return conn, guard_cur, server_cur


def test_execute_safe_query_blocks_write_without_touching_db() -> None:
    conn, _, _ = _mock_conn()
    res = execute_safe_query(conn, "DELETE FROM orders WHERE order_id = 1")
    assert res.success is False
    assert "Blocked" in res.error_message
    conn.transaction.assert_not_called()


def test_execute_safe_query_enforces_read_only_timeout_and_row_truncation() -> None:
    rows = [(i, f"row-{i}") for i in range(6)]  # max_rows=5 -> 6 fetched -> truncated
    conn, guard_cur, _ = _mock_conn(rows=rows, cols=["id", "label"])
    res = execute_safe_query(conn, "SELECT order_id, status FROM orders", timeout_ms=3000, max_rows=5)

    assert res.success is True
    assert res.was_truncated is True
    assert res.rows_returned == 5
    assert res.columns == ["id", "label"]
    executed_sqls = [call.args[0] for call in guard_cur.execute.call_args_list]
    assert "SET TRANSACTION READ ONLY" in executed_sqls
    assert "SET LOCAL statement_timeout = 3000" in executed_sqls


def test_run_explain_plan_blocks_unsafe_query_and_runs_read_only_tx() -> None:
    conn, _, _ = _mock_conn()
    blocked = run_explain_plan(conn, "DROP TABLE orders")
    assert blocked.success is False
    conn.transaction.assert_not_called()

    sample_plan = [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "orders", "Total Cost": 10.0, "Plan Rows": 5}}]
    conn2, guard_cur, _ = _mock_conn(explain_payload=sample_plan)
    ok = run_explain_plan(conn2, "SELECT order_id FROM orders", analyze=True, buffers=True, timeout_ms=4000)
    assert ok.success is True
    assert ok.raw_plan_json == sample_plan
    executed_sqls = [call.args[0] for call in guard_cur.execute.call_args_list]
    assert "SET TRANSACTION READ ONLY" in executed_sqls
    assert "SET LOCAL statement_timeout = 4000" in executed_sqls
    assert any(s.startswith("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)") for s in executed_sqls)
