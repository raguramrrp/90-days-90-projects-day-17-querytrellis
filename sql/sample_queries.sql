-- =============================================================================
-- QueryTrellis Curated Sample SQL Queries
-- =============================================================================
-- Organized to showcase PostgreSQL query patterns, anti-patterns, indexed vs
-- non-indexed predicates, joins, CTEs, window functions, and optimization pairs.

-- [1] SELECT with WHERE (Non-indexed FK column)
SELECT order_id, customer_id, order_date, status, total_amount
FROM orders
WHERE customer_id = 420;

-- [2] Filtering on Indexed Column (PK / category_id)
SELECT product_id, sku, product_name, brand, unit_price
FROM products
WHERE category_id = 5 AND unit_price >= 50.00
ORDER BY unit_price DESC
LIMIT 50;

-- [3] Multiple JOINs (Orders, Customers, Order Items, Products)
SELECT
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
LIMIT 100;

-- [4] GROUP BY & Aggregation (Revenue by Category and Sales Channel)
SELECT
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
ORDER BY gross_revenue DESC;

-- [5] CTE + Window Function (Top Products Ranked per Category)
WITH product_sales AS (
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
LIMIT 75;

-- [6] Anti-pattern: Function on Filtered Indexed Column + SELECT *
SELECT *
FROM customers
WHERE LOWER(email) = 'customer125@example.com';

-- [7] Optimized: Sargable Date Range (vs EXTRACT(YEAR FROM order_date))
-- Baseline slow form: SELECT order_id, total_amount FROM orders WHERE EXTRACT(YEAR FROM order_date) = 2025;
SELECT order_id, customer_id, order_date, total_amount
FROM orders
WHERE order_date >= TIMESTAMPTZ '2025-01-01 00:00:00+00'
  AND order_date < TIMESTAMPTZ '2026-01-01 00:00:00+00'
ORDER BY order_date DESC
LIMIT 200;

-- [8] Anti-pattern: Correlated Subquery in SELECT List
SELECT
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
LIMIT 100;

-- [9] Optimized: Pre-aggregated CTE + LEFT JOIN (Replaces Correlated Subquery)
WITH delivered_counts AS (
    SELECT customer_id, COUNT(*) AS delivered_orders
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
LIMIT 100;

-- [10] Anti-pattern: Leading Wildcard LIKE + Large OFFSET Pagination
SELECT order_id, customer_id, order_date, total_amount
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE c.email LIKE '%example.com'
ORDER BY o.order_date DESC, o.order_id DESC
OFFSET 15000
LIMIT 50;
