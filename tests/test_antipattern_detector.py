"""Unit tests for nuanced SQL anti-pattern detection."""
from __future__ import annotations

from src.db.connection_manager import DatabaseCatalog
from src.sql_analysis.antipattern_detector import detect_antipatterns
from src.sql_analysis.parser_validator import validate_read_only_sql


def _rule_ids(sql: str, catalog: DatabaseCatalog | None = None) -> set[str]:
    val = validate_read_only_sql(sql)
    findings = detect_antipatterns(val, catalog=catalog)
    return {f.rule_id for f in findings}


def test_clean_count_star_not_flagged_as_select_star(sample_catalog: DatabaseCatalog) -> None:
    rules = _rule_ids("SELECT COUNT(*) FROM categories", catalog=sample_catalog)
    assert "AP001" not in rules


def test_detects_select_star_and_missing_where_on_large_table(sample_catalog: DatabaseCatalog) -> None:
    rules = _rule_ids("SELECT * FROM orders", catalog=sample_catalog)
    assert "AP001" in rules
    assert "AP002" in rules
    findings = detect_antipatterns(validate_read_only_sql("SELECT * FROM orders"), catalog=sample_catalog)
    ap001 = next(f for f in findings if f.rule_id == "AP001")
    assert ap001.when_acceptable  # Nuanced context always present
    assert ap001.suggested_improvement


def test_detects_non_sargable_function_and_leading_wildcard(sample_catalog: DatabaseCatalog) -> None:
    rules = _rule_ids(
        "SELECT customer_id FROM customers WHERE LOWER(email) LIKE '%example.com'",
        catalog=sample_catalog,
    )
    assert "AP003" in rules
    assert "AP004" in rules


def test_detects_correlated_subquery_and_repeated_subquery() -> None:
    sql = """
    SELECT c.customer_id,
           (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.customer_id) AS cnt1,
           (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.customer_id) AS cnt2
    FROM customers c
    WHERE c.country = 'India'
    """
    rules = _rule_ids(sql)
    assert "AP006" in rules
    assert "AP007" in rules


def test_detects_unnecessary_distinct_with_pk(sample_catalog: DatabaseCatalog) -> None:
    rules = _rule_ids(
        "SELECT DISTINCT customer_id, email FROM customers WHERE country = 'India'",
        catalog=sample_catalog,
    )
    assert "AP005" in rules


def test_detects_or_inner_order_by_and_large_offset() -> None:
    sql = """
    WITH ordered_sub AS (
        SELECT order_id, customer_id, status FROM orders ORDER BY order_id DESC
    )
    SELECT order_id FROM ordered_sub
    WHERE customer_id = 10 OR status = 'pending'
    ORDER BY order_id
    OFFSET 2500 LIMIT 50
    """
    rules = _rule_ids(sql)
    assert "AP008" in rules
    assert "AP009" in rules
    assert "AP010" in rules


def test_detects_implicit_type_conversion_with_catalog(sample_catalog: DatabaseCatalog) -> None:
    rules = _rule_ids(
        "SELECT order_id FROM orders WHERE customer_id = '420' AND status = 1",
        catalog=sample_catalog,
    )
    assert "AP011" in rules


def test_detects_nested_wrapper_repeated_expr_and_bad_joins() -> None:
    sql = """
    SELECT *
    FROM (
        SELECT o.order_id, UPPER(c.country) AS ucountry
        FROM orders o, customers c
        WHERE UPPER(c.country) = 'INDIA'
    ) sub
    """
    rules = _rule_ids(sql)
    assert "AP012" in rules
    assert "AP013" in rules
    assert "AP014" in rules

    ineff_join = _rule_ids(
        "SELECT o.order_id FROM orders o JOIN customers c ON LOWER(c.email) = LOWER(o.status)"
    )
    assert "AP015" in ineff_join
