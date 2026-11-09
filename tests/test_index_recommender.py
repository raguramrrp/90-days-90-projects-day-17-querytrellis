"""Unit tests for the rule-based PostgreSQL index recommendation engine."""
from __future__ import annotations

from src.advisor.index_recommender import recommend_indexes
from src.db.connection_manager import DatabaseCatalog
from src.sql_analysis.parser_validator import validate_read_only_sql


def test_recommends_index_for_unindexed_customer_id_and_skips_tiny_table(
    sample_catalog: DatabaseCatalog,
) -> None:
    val = validate_read_only_sql("SELECT order_id, total_amount FROM orders WHERE customer_id = 420")
    recs = recommend_indexes(val, catalog=sample_catalog)
    assert any(
        "CREATE INDEX" in r.suggested_sql and "orders(customer_id)" in r.suggested_sql
        for r in recs
    )
    assert any(r.index_type == "Covering (INCLUDE)" for r in recs)

    # Small table 'categories' (25 rows) should NOT get index recommendations
    small_val = validate_read_only_sql("SELECT category_id FROM categories WHERE category_name = 'Audio'")
    small_recs = recommend_indexes(small_val, catalog=sample_catalog)
    assert small_recs == []


def test_avoids_duplicate_recommendation_for_already_indexed_column(
    sample_catalog: DatabaseCatalog,
) -> None:
    val = validate_read_only_sql("SELECT product_id, brand FROM products WHERE category_id = 5")
    recs = recommend_indexes(val, catalog=sample_catalog)
    # products(category_id) already has idx_products_category_id -> should not recommend single-col idx on category_id
    assert not any(
        r.index_type == "Single-Column B-tree" and r.columns == ["category_id"]
        for r in recs
    )


def test_recommends_composite_esr_and_partial_index(sample_catalog: DatabaseCatalog) -> None:
    sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE status = 'pending'
      AND customer_id = 99
      AND order_date >= '2025-01-01'
    ORDER BY order_date DESC
    """
    val = validate_read_only_sql(sql)
    recs = recommend_indexes(val, catalog=sample_catalog)
    types = {r.index_type for r in recs}
    assert "Composite B-tree" in types
    assert "Partial B-tree" in types


def test_does_not_recommend_btree_for_non_sargable_function(sample_catalog: DatabaseCatalog) -> None:
    val = validate_read_only_sql("SELECT customer_id FROM customers WHERE LOWER(email) = 'a@b.com'")
    recs = recommend_indexes(val, catalog=sample_catalog)
    assert recs == []
