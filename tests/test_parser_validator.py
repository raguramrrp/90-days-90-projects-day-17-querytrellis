"""Unit tests for SQL parsing, formatting, single-statement checks, and read-only validation."""
from __future__ import annotations

import pytest

from src.sql_analysis.formatter import format_sql
from src.sql_analysis.parser_validator import validate_read_only_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT order_id, total_amount FROM orders WHERE customer_id = 42;",
        "WITH cte AS (SELECT customer_id, COUNT(*) AS cnt FROM orders GROUP BY customer_id) SELECT * FROM cte",
        "SELECT product_id, DENSE_RANK() OVER (PARTITION BY category_id ORDER BY unit_price DESC) FROM products",
        "SELECT customer_id FROM customers UNION ALL SELECT customer_id FROM orders",
        "SELECT /* comment */ COUNT(*) FROM orders",
    ],
)
def test_valid_read_only_queries_pass(sql: str) -> None:
    res = validate_read_only_sql(sql)
    assert res.is_valid is True
    assert res.is_read_only is True
    assert res.parsed_info is not None
    assert res.error_message == ""


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders (customer_id) VALUES (1)",
        "UPDATE orders SET status = 'cancelled' WHERE order_id = 1",
        "DELETE FROM orders WHERE order_id = 1",
        "DROP TABLE orders",
        "ALTER TABLE orders ADD COLUMN note TEXT",
        "TRUNCATE TABLE orders",
        "CREATE INDEX idx_x ON orders(customer_id)",
        "GRANT ALL ON orders TO public",
        "WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted",
        "SELECT * INTO new_orders FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT * FROM orders FOR SHARE",
        "EXPLAIN SELECT * FROM orders",
        "SELECT pg_sleep(5)",
        "SELECT pg_terminate_backend(1234)",
    ],
)
def test_unsafe_statements_rejected(sql: str) -> None:
    res = validate_read_only_sql(sql)
    assert res.is_read_only is False
    assert res.error_message != ""


def test_multiple_statements_rejected() -> None:
    res = validate_read_only_sql("SELECT 1; SELECT 2;")
    assert res.is_valid is False
    assert res.is_read_only is False
    assert res.rejected_operation == "MULTIPLE_STATEMENTS"


def test_empty_and_malformed_sql() -> None:
    empty = validate_read_only_sql("   -- just a comment\n ")
    assert empty.is_valid is False
    assert empty.is_read_only is False

    bad = validate_read_only_sql("SELECT FROM WHERE ???")
    assert bad.is_valid is False
    assert bad.is_read_only is False
    assert "syntax" in bad.error_message.lower() or "parse" in bad.error_message.lower()


def test_metadata_extraction_tables_joins_limits() -> None:
    sql = """
    SELECT o.order_id, c.email
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.status = 'delivered'
    ORDER BY o.order_date DESC
    OFFSET 500
    LIMIT 25
    """
    res = validate_read_only_sql(sql)
    assert res.is_read_only
    info = res.parsed_info
    assert info is not None
    assert {t.table for t in info.tables} == {"orders", "customers"}
    assert info.alias_to_table["o"] == "orders"
    assert info.alias_to_table["c"] == "customers"
    assert info.limit_value == 25
    assert info.offset_value == 500
    assert len(info.joins) == 1
    assert info.joins[0].has_on_condition is True


def test_sql_formatter_pretty_prints_and_handles_invalid() -> None:
    formatted, err = format_sql("select order_id, customer_id from orders where status='delivered';")
    assert err is None
    assert "SELECT" in formatted
    assert "\n" in formatted

    orig, ferr = format_sql("SELECT FROM ((")
    assert ferr is not None
    assert orig == "SELECT FROM (("
