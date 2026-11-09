"""Curated sample SQL queries covering PostgreSQL patterns and optimization pairs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SampleQuery:
    """Built-in SQL example for the Query Editor and Benchmark Lab."""

    key: str
    title: str
    category: str
    description: str
    sql: str
    suggested_optimization: str | None = None


SAMPLE_QUERIES: list[SampleQuery] = [
    SampleQuery(
        key="non_indexed_fk_where",
        title="1. Non-Indexed Filter (orders.customer_id)",
        category="Indexed vs Non-Indexed Filtering",
        description="Filters orders by customer_id (unindexed FK initially) — demonstrates Seq Scan and single-column index recommendation.",
        sql="""SELECT
    order_id,
    customer_id,
    order_date,
    status,
    total_amount
FROM orders
WHERE customer_id = 420
ORDER BY order_date DESC;""",
    ),
    SampleQuery(
        key="indexed_category_filter",
        title="2. Indexed Column Filter (products.category_id)",
        category="Indexed vs Non-Indexed Filtering",
        description="Filters products using the pre-existing idx_products_category_id index combined with unit_price.",
        sql="""SELECT
    product_id,
    sku,
    product_name,
    brand,
    unit_price
FROM products
WHERE category_id = 5
  AND unit_price >= 50.00
ORDER BY unit_price DESC
LIMIT 50;""",
    ),
    SampleQuery(
        key="multi_join_recent_orders",
        title="3. Multi-Table JOIN (4 Tables)",
        category="Multiple JOINs",
        description="Joins orders, customers, order_items, and products for recent delivered orders.",
        sql="""SELECT
    o.order_id,
    o.order_date,
    c.first_name || ' ' || c.last_name AS customer_name,
    c.country,
    p.product_name,
    oi.quantity,
    oi.line_total
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status = 'delivered'
  AND o.order_date >= NOW() - INTERVAL '90 days'
ORDER BY o.order_date DESC
LIMIT 100;""",
    ),
    SampleQuery(
        key="group_by_revenue",
        title="4. GROUP BY Revenue Aggregation",
        category="GROUP BY & Aggregation",
        description="Aggregates order counts, units sold, and revenue across categories and sales channels.",
        sql="""SELECT
    cat.category_name,
    o.sales_channel,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.line_total), 2) AS gross_revenue
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN categories cat ON cat.category_id = p.category_id
WHERE o.status IN ('shipped', 'delivered')
GROUP BY cat.category_name, o.sales_channel
ORDER BY gross_revenue DESC;""",
    ),
    SampleQuery(
        key="cte_window_ranking",
        title="5. CTE + Window Function Ranking",
        category="CTEs & Window Functions",
        description="Computes top-performing products ranked within each category using DENSE_RANK().",
        sql="""WITH product_sales AS (
    SELECT
        p.category_id,
        p.product_id,
        p.product_name,
        SUM(oi.line_total) AS total_revenue,
        SUM(oi.quantity) AS total_units
    FROM order_items oi
    JOIN products p ON p.product_id = oi.product_id
    GROUP BY p.category_id, p.product_id, p.product_name
)
SELECT
    c.category_name,
    ps.product_name,
    ROUND(ps.total_revenue, 2) AS total_revenue,
    ps.total_units,
    DENSE_RANK() OVER (
        PARTITION BY ps.category_id
        ORDER BY ps.total_revenue DESC
    ) AS category_rank
FROM product_sales ps
JOIN categories c ON c.category_id = ps.category_id
ORDER BY c.category_name, category_rank
LIMIT 75;""",
    ),
    SampleQuery(
        key="non_sargable_function",
        title="6. Anti-pattern: Function on Filtered Indexed Column",
        category="Optimization Pair (Before)",
        description="Uses LOWER(email) + SELECT * on customers, bypassing the B-tree index on email.",
        sql="""SELECT *
FROM customers
WHERE LOWER(email) = 'customer125@example.com';""",
        suggested_optimization="""SELECT
    customer_id,
    first_name,
    last_name,
    email,
    country,
    segment
FROM customers
WHERE email = 'customer125@example.com';""",
    ),
    SampleQuery(
        key="correlated_subquery_slow",
        title="7. Anti-pattern: Correlated Subquery in SELECT",
        category="Optimization Pair (Before)",
        description="Counts delivered orders per customer via correlated scalar subquery vs grouped CTE LEFT JOIN.",
        sql="""SELECT
    c.customer_id,
    c.email,
    c.segment,
    (
        SELECT COUNT(*)
        FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.status = 'delivered'
    ) AS delivered_orders
FROM customers c
WHERE c.country = 'India'
LIMIT 100;""",
        suggested_optimization="""WITH delivered_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS delivered_orders
    FROM orders
    WHERE status = 'delivered'
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.email,
    c.segment,
    COALESCE(dc.delivered_orders, 0) AS delivered_orders
FROM customers c
LEFT JOIN delivered_counts dc ON dc.customer_id = c.customer_id
WHERE c.country = 'India'
LIMIT 100;""",
    ),
    SampleQuery(
        key="leading_wildcard_offset",
        title="8. Anti-pattern: Leading Wildcard LIKE + Large OFFSET",
        category="Optimization Pair (Before)",
        description="Combines leading wildcard LIKE '%example.com' with OFFSET 15000 pagination.",
        sql="""SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.total_amount
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE c.email LIKE '%example.com'
ORDER BY o.order_date DESC, o.order_id DESC
OFFSET 15000
LIMIT 50;""",
        suggested_optimization="""SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.total_amount
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE c.email LIKE 'customer1%'
  AND (o.order_date, o.order_id) < (TIMESTAMPTZ '2025-09-01 00:00:00+00', 40000)
ORDER BY o.order_date DESC, o.order_id DESC
LIMIT 50;""",
    ),
    SampleQuery(
        key="non_sargable_date_extract",
        title="9. Anti-pattern: EXTRACT(YEAR FROM order_date) vs Date Range",
        category="Optimization Pair (Before)",
        description="Applies EXTRACT(YEAR) on order_date instead of an index-friendly half-open range.",
        sql="""SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM orders
WHERE EXTRACT(YEAR FROM order_date) = 2025
ORDER BY order_date DESC
LIMIT 200;""",
        suggested_optimization="""SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM orders
WHERE order_date >= TIMESTAMPTZ '2025-01-01 00:00:00+00'
  AND order_date < TIMESTAMPTZ '2026-01-01 00:00:00+00'
ORDER BY order_date DESC
LIMIT 200;""",
    ),
]
