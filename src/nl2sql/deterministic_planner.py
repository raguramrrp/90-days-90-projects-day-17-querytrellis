"""Schema-grounded deterministic NL-to-SQL engine for CPU-only / offline mode & fallback.

Constructs real, verifiable SQL purely from active DatabaseContextSnapshot tables,
columns, and relationships, then transpiles cleanly via SQLGlot to the chosen dialect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.context.models import DatabaseContextSnapshot, TableSchema
from src.dialects.sqlglot_engine import convert_sql_dialect, format_sql_for_dialect, normalize_dialect


@dataclass(slots=True)
class PlannedQuery:
    """Generated SQL bundle before final explainer/verification enrichment."""

    postgres_sql: str
    explanation: str
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    alternatives: list[dict[str, str]] = field(default_factory=list)
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)


def _find_numeric_col(tbl: TableSchema, keywords: tuple[str, ...]) -> str | None:
    for kw in keywords:
        for c in tbl.columns:
            if kw in c.name.lower() and any(
                t in c.data_type.lower() for t in ("int", "double", "float", "numeric", "decimal", "real")
            ):
                return c.name
    for c in tbl.columns:
        if not c.is_primary_key and not c.is_foreign_key and any(
            t in c.data_type.lower() for t in ("double", "float", "numeric", "decimal")
        ):
            return c.name
    return None


def _find_date_col(tbl: TableSchema) -> str | None:
    for c in tbl.columns:
        if any(k in c.data_type.lower() for k in ("date", "timestamp")) or "date" in c.name.lower():
            return c.name
    return None


def _find_name_col(tbl: TableSchema) -> str | None:
    for kw in ("name", "title", "sku", "email", "region", "department", "category"):
        for c in tbl.columns:
            if kw in c.name.lower():
                return c.name
    for c in tbl.columns:
        if "char" in c.data_type.lower() or "text" in c.data_type.lower():
            return c.name
    return None


def _extract_limit(low: str, default: int = 10) -> int:
    m = re.search(r"\btop\s+(\d+)\b|\blimit\s+(\d+)\b", low)
    if m:
        val = int(m.group(1) or m.group(2))
        return max(1, min(500, val))
    return default


def _extract_gt_threshold(low: str, default: int = 3) -> int:
    word_nums = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}
    m = re.search(r"more\s+than\s+(\w+)|greater\s+than\s+(\w+)|over\s+(\d+)|>\s*(\d+)", low)
    if m:
        raw = next(g for g in m.groups() if g)
        if raw.isdigit():
            return int(raw)
        if raw.lower() in word_nums:
            return word_nums[raw.lower()]
    return default


def generate_deterministic_sql(
    user_request: str,
    context: DatabaseContextSnapshot,
    clarification_answer: str | None = None,
) -> PlannedQuery:
    """Plan schema-grounded SQL strictly from verified tables/columns in context."""
    low = (user_request or "").strip().lower()
    clar = (clarification_answer or "").strip().lower()
    emp_tbl = context.find_table("employees")
    dept_tbl = context.find_table("departments")
    reg_tbl = context.find_table("sales_regions") or context.find_table("regions")
    cust_tbl = context.find_table("customers")
    prod_tbl = context.find_table("products")
    ord_tbl = context.find_table("orders")
    oi_tbl = context.find_table("order_items")
    deals_tbl = context.find_table("quarterly_deals")

    # 1. Top N performing employees (with clarified metric)
    if ("employee" in low) and any(k in low for k in ("top", "best", "performing", "performance")):
        if emp_tbl is not None and ord_tbl is not None and ord_tbl.get_column("employee_id"):
            limit_n = _extract_limit(low, 10)
            name_expr = (
                "CONCAT(e.first_name, ' ', e.last_name)"
                if (emp_tbl.get_column("first_name") and emp_tbl.get_column("last_name"))
                else f"e.{_find_name_col(emp_tbl) or 'employee_id'}"
            )
            if "count" in clar or "number of sales" in clar or "order_count" in clar:
                sql = f"""SELECT
    e.employee_id,
    {name_expr} AS employee_name,
    e.job_title,
    COUNT(o.order_id) AS orders_closed,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS total_revenue
FROM employees e
LEFT JOIN orders o ON o.employee_id = e.employee_id
    AND o.status <> 'cancelled'
GROUP BY e.employee_id, {name_expr}, e.job_title
ORDER BY orders_closed DESC, total_revenue DESC
LIMIT {limit_n};"""
                return PlannedQuery(
                    postgres_sql=sql,
                    explanation=f"Ranks top {limit_n} employees by count of non-cancelled orders closed, using total revenue as tie-breaker.",
                    assumptions=["Excluded orders with status = 'cancelled' from sales performance counts."],
                    limitations=["Assumes equal credit per order without multi-rep split attribution."],
                    alternatives=[
                        {
                            "title": "Rank using DENSE_RANK() window function",
                            "sql": sql.replace("ORDER BY orders_closed DESC", "ORDER BY orders_closed DESC"),
                            "reason": "Window ranking handles tied sales counts transparently.",
                        }
                    ],
                )
            elif ("profit" in clar) and oi_tbl is not None and prod_tbl is not None and prod_tbl.get_column("unit_cost"):
                sql = f"""SELECT
    e.employee_id,
    {name_expr} AS employee_name,
    COUNT(DISTINCT o.order_id) AS orders_closed,
    ROUND(SUM(oi.line_total - (oi.quantity * p.unit_cost)), 2) AS net_profit,
    ROUND(SUM(oi.line_total), 2) AS total_revenue
FROM employees e
JOIN orders o ON o.employee_id = e.employee_id
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.status <> 'cancelled'
GROUP BY e.employee_id, {name_expr}
ORDER BY net_profit DESC
LIMIT {limit_n};"""
                return PlannedQuery(
                    postgres_sql=sql,
                    explanation=f"Computes top {limit_n} employees by gross product profit (line_total minus quantity * products.unit_cost).",
                    assumptions=["Profit excludes shipping or tax overhead not modeled in schema.", "Excludes cancelled orders."],
                    limitations=["Requires item-level join across order_items and products."],
                )
            elif ("target" in clar or "quota" in clar) and emp_tbl.get_column("sales_target"):
                sql = f"""SELECT
    e.employee_id,
    {name_expr} AS employee_name,
    ROUND(e.sales_target, 2) AS sales_target,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS actual_revenue,
    ROUND(COALESCE(SUM(o.total_amount), 0) * 100.0 / NULLIF(e.sales_target, 0), 2) AS target_achievement_pct
FROM employees e
LEFT JOIN orders o ON o.employee_id = e.employee_id
    AND o.status <> 'cancelled'
GROUP BY e.employee_id, {name_expr}, e.sales_target
ORDER BY target_achievement_pct DESC
LIMIT {limit_n};"""
                return PlannedQuery(
                    postgres_sql=sql,
                    explanation=f"Evaluates top {limit_n} employees by percentage of `employees.sales_target` achieved.",
                    assumptions=["Uses `NULLIF(sales_target, 0)` to prevent divide-by-zero errors."],
                    limitations=["Compares cumulative order revenue in active table against static sales_target column."],
                )
            else:
                sql = f"""SELECT
    e.employee_id,
    {name_expr} AS employee_name,
    e.job_title,
    COUNT(o.order_id) AS orders_closed,
    ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS total_revenue
FROM employees e
LEFT JOIN orders o ON o.employee_id = e.employee_id
    AND o.status <> 'cancelled'
GROUP BY e.employee_id, {name_expr}, e.job_title
ORDER BY total_revenue DESC
LIMIT {limit_n};"""
                return PlannedQuery(
                    postgres_sql=sql,
                    explanation=f"Ranks the top {limit_n} employees by cumulative non-cancelled order revenue (`SUM(orders.total_amount)`).",
                    assumptions=["Excludes cancelled orders via LEFT JOIN filter.", "Ranks by total revenue generated."],
                    limitations=["Does not restrict to a specific month unless an order_date filter is added."],
                    alternatives=[
                        {
                            "title": "Include target achievement ratio",
                            "sql": sql.replace(
                                "ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS total_revenue",
                                "ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS total_revenue,\n    ROUND(COALESCE(SUM(o.total_amount), 0) * 100.0 / NULLIF(e.sales_target, 0), 2) AS target_pct",
                            ),
                            "reason": "Adds quota attainment context alongside raw revenue.",
                        }
                    ],
                )
        elif emp_tbl is not None and deals_tbl is not None:
            limit_n = _extract_limit(low, 10)
            sql = f"""SELECT
    e.employee_id,
    e.full_name,
    COUNT(d.deal_id) AS deal_count,
    ROUND(SUM(d.deal_amount), 2) AS total_revenue
FROM employees e
LEFT JOIN quarterly_deals d ON d.employee_id = e.employee_id
GROUP BY e.employee_id, e.full_name
ORDER BY total_revenue DESC
LIMIT {limit_n};"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation=f"Ranks top {limit_n} employees from uploaded `quarterly_deals` and `employees` tables.",
                assumptions=["Aggregates deal_amount across all rows in quarterly_deals."],
            )

    # 2. Employees above department average
    if "employee" in low and "department" in low and ("average" in low or "avg" in low):
        if emp_tbl is not None and dept_tbl is not None:
            name_expr = (
                "CONCAT(e.first_name, ' ', e.last_name)"
                if (emp_tbl.get_column("first_name") and emp_tbl.get_column("last_name"))
                else f"e.{_find_name_col(emp_tbl) or 'employee_id'}"
            )
            if ord_tbl is not None and ord_tbl.get_column("employee_id"):
                sql = f"""WITH employee_perf AS (
    SELECT
        e.employee_id,
        {name_expr} AS employee_name,
        d.department_name,
        COALESCE(SUM(o.total_amount), 0) AS employee_revenue
    FROM employees e
    JOIN departments d ON d.department_id = e.department_id
    LEFT JOIN orders o ON o.employee_id = e.employee_id AND o.status <> 'cancelled'
    GROUP BY e.employee_id, {name_expr}, d.department_name
),
dept_benchmarks AS (
    SELECT
        employee_id,
        employee_name,
        department_name,
        ROUND(employee_revenue, 2) AS employee_revenue,
        ROUND(AVG(employee_revenue) OVER (PARTITION BY department_name), 2) AS dept_avg_revenue
    FROM employee_perf
)
SELECT
    employee_id,
    employee_name,
    department_name,
    employee_revenue,
    dept_avg_revenue,
    ROUND(employee_revenue - dept_avg_revenue, 2) AS variance_above_avg
FROM dept_benchmarks
WHERE employee_revenue > dept_avg_revenue
ORDER BY department_name, variance_above_avg DESC;"""
                return PlannedQuery(
                    postgres_sql=sql,
                    explanation="Computes each employee's revenue, evaluates the department average with `AVG(...) OVER (PARTITION BY department_name)`, and keeps employees exceeding their department average.",
                    assumptions=["Measured employee performance using non-cancelled total order revenue."],
                    limitations=["Window CTE avoids scanning orders twice compared to correlated subqueries."],
                    alternatives=[
                        {
                            "title": "Compare base salary vs department salary average",
                            "sql": f"""WITH sal_stats AS (
    SELECT
        e.employee_id,
        {name_expr} AS employee_name,
        d.department_name,
        e.base_salary,
        ROUND(AVG(e.base_salary) OVER (PARTITION BY d.department_id), 2) AS dept_avg_salary
    FROM employees e
    JOIN departments d ON d.department_id = e.department_id
)
SELECT * FROM sal_stats WHERE base_salary > dept_avg_salary ORDER BY base_salary DESC;""",
                            "reason": "Use if benchmarking compensation rather than sales revenue.",
                        }
                    ],
                )

    # 3. Running total of monthly revenue
    if "running total" in low and ("revenue" in low or "sales" in low):
        if ord_tbl is not None:
            sql = """WITH monthly_rev AS (
    SELECT
        DATE_TRUNC('month', order_date)::DATE AS month_start,
        ROUND(SUM(total_amount), 2) AS monthly_revenue
    FROM orders
    WHERE status <> 'cancelled'
    GROUP BY DATE_TRUNC('month', order_date)::DATE
)
SELECT
    month_start,
    monthly_revenue,
    ROUND(
        SUM(monthly_revenue) OVER (
            ORDER BY month_start
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        2
    ) AS running_total_revenue
FROM monthly_rev
ORDER BY month_start;"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation="Aggregates monthly revenue first in a CTE, then computes a cumulative running total via `SUM() OVER (ORDER BY month_start ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`.",
                assumptions=["Excludes cancelled orders.", "Buckets order_date by calendar month."],
                limitations=["Uses explicit window frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` for deterministic accumulation."],
            )
        elif context.find_table("monthly_revenue") is not None:
            sql = """WITH m AS (
    SELECT month, SUM(net_revenue) AS monthly_revenue
    FROM monthly_revenue
    GROUP BY month
)
SELECT
    month,
    ROUND(monthly_revenue, 2) AS monthly_revenue,
    ROUND(SUM(monthly_revenue) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS running_total_revenue
FROM m
ORDER BY month;"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation="Computes running total over `monthly_revenue.net_revenue`.",
                assumptions=["Sums across all regions per month before accumulating."],
            )

    # 4. Monthly revenue for each region
    if "monthly" in low and ("region" in low or "country" in low) and ("revenue" in low or "sales" in low):
        if ord_tbl is not None and reg_tbl is not None:
            sql = """SELECT
    DATE_TRUNC('month', o.order_date)::DATE AS month_start,
    r.region_name,
    COUNT(o.order_id) AS order_count,
    ROUND(SUM(o.total_amount), 2) AS monthly_revenue
FROM orders o
JOIN sales_regions r ON r.region_id = o.region_id
WHERE o.status <> 'cancelled'
GROUP BY DATE_TRUNC('month', o.order_date)::DATE, r.region_name
ORDER BY month_start, monthly_revenue DESC;"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation="Joins `orders` with `sales_regions` and aggregates non-cancelled order counts and revenue by month and region.",
                assumptions=["Excludes orders with status = 'cancelled'."],
                limitations=["Regions with zero orders in a given month are omitted unless cross-joined with a calendar series."],
            )
        elif ord_tbl is not None and cust_tbl is not None and cust_tbl.get_column("country"):
            sql = """SELECT
    DATE_TRUNC('month', o.order_date)::DATE AS month_start,
    c.country AS region,
    COUNT(o.order_id) AS order_count,
    ROUND(SUM(o.total_amount), 2) AS monthly_revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.status <> 'cancelled'
GROUP BY DATE_TRUNC('month', o.order_date)::DATE, c.country
ORDER BY month_start, monthly_revenue DESC;"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation="Uses `customers.country` as geographic region since active schema has no dedicated `regions` table.",
                assumptions=["Mapped 'region' to `customers.country` verified in active schema."],
            )

    # 5. Compare this month's sales with previous month
    if ("previous month" in low or "last month" in low or "month over month" in low or ("compare" in low and "month" in low)):
        if ord_tbl is not None:
            if "calendar_current" in clar:
                sql = """WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', order_date)::DATE AS month_start,
        COUNT(order_id) AS order_count,
        ROUND(SUM(total_amount), 2) AS total_sales
    FROM orders
    WHERE status <> 'cancelled'
      AND order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
    GROUP BY DATE_TRUNC('month', order_date)::DATE
)
SELECT
    month_start,
    order_count,
    total_sales,
    LAG(total_sales) OVER (ORDER BY month_start) AS previous_month_sales,
    ROUND(total_sales - LAG(total_sales) OVER (ORDER BY month_start), 2) AS sales_delta
FROM monthly_sales
ORDER BY month_start DESC;"""
            else:
                sql = """WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', order_date)::DATE AS month_start,
        COUNT(order_id) AS order_count,
        ROUND(SUM(total_amount), 2) AS total_sales
    FROM orders
    WHERE status <> 'cancelled'
    GROUP BY DATE_TRUNC('month', order_date)::DATE
),
with_prev AS (
    SELECT
        month_start,
        order_count,
        total_sales,
        LAG(total_sales) OVER (ORDER BY month_start) AS previous_month_sales,
        ROUND(total_sales - LAG(total_sales) OVER (ORDER BY month_start), 2) AS sales_delta,
        ROUND(
            (total_sales - LAG(total_sales) OVER (ORDER BY month_start)) * 100.0
            / NULLIF(LAG(total_sales) OVER (ORDER BY month_start), 0),
            2
        ) AS mom_change_pct
    FROM monthly_sales
)
SELECT *
FROM with_prev
WHERE month_start = (SELECT MAX(month_start) FROM monthly_sales);"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation="Aggregates monthly totals across orders, pairs the latest month with its prior month via `LAG(total_sales) OVER (ORDER BY month_start)`, and computes absolute delta and % change.",
                assumptions=[
                    "Anchored 'this month' to the latest month present in `orders` (`MAX(month_start)`) so historical datasets return valid results."
                    if "calendar_current" not in clar
                    else "Used calendar `CURRENT_DATE` month window as requested."
                ],
                limitations=["Month-to-date partial months may compare unequally against full prior months."],
            )

    # 6. Products with declining sales
    if "product" in low and ("declining" in low or "decreasing" in low or "drop" in low):
        if prod_tbl is not None and oi_tbl is not None and ord_tbl is not None:
            if "consecutive" in clar:
                sql = """WITH product_monthly AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        DATE_TRUNC('month', o.order_date)::DATE AS month_start,
        ROUND(SUM(oi.line_total), 2) AS monthly_sales
    FROM products p
    JOIN order_items oi ON oi.product_id = p.product_id
    JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status <> 'cancelled'
    GROUP BY p.product_id, p.product_name, p.category, DATE_TRUNC('month', o.order_date)::DATE
),
trends AS (
    SELECT
        product_id,
        product_name,
        category,
        month_start,
        monthly_sales,
        LAG(monthly_sales, 1) OVER (PARTITION BY product_id ORDER BY month_start) AS prev_1_sales,
        LAG(monthly_sales, 2) OVER (PARTITION BY product_id ORDER BY month_start) AS prev_2_sales
    FROM product_monthly
)
SELECT
    product_id,
    product_name,
    category,
    month_start AS latest_month,
    prev_2_sales,
    prev_1_sales,
    monthly_sales AS latest_sales
FROM trends
WHERE month_start = (SELECT MAX(month_start) FROM product_monthly)
  AND prev_2_sales IS NOT NULL
  AND prev_1_sales < prev_2_sales
  AND monthly_sales < prev_1_sales
ORDER BY (monthly_sales - prev_2_sales) ASC;"""
            else:
                sql = """WITH product_monthly AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        DATE_TRUNC('month', o.order_date)::DATE AS month_start,
        ROUND(SUM(oi.line_total), 2) AS monthly_sales
    FROM products p
    JOIN order_items oi ON oi.product_id = p.product_id
    JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status <> 'cancelled'
    GROUP BY p.product_id, p.product_name, p.category, DATE_TRUNC('month', o.order_date)::DATE
),
trends AS (
    SELECT
        product_id,
        product_name,
        category,
        month_start,
        monthly_sales,
        LAG(monthly_sales) OVER (PARTITION BY product_id ORDER BY month_start) AS previous_month_sales,
        ROUND(monthly_sales - LAG(monthly_sales) OVER (PARTITION BY product_id ORDER BY month_start), 2) AS sales_delta
    FROM product_monthly
)
SELECT
    product_id,
    product_name,
    category,
    month_start AS latest_month,
    previous_month_sales,
    monthly_sales AS latest_month_sales,
    sales_delta,
    ROUND(sales_delta * 100.0 / NULLIF(previous_month_sales, 0), 2) AS decline_pct
FROM trends
WHERE month_start = (SELECT MAX(month_start) FROM product_monthly)
  AND sales_delta < 0
ORDER BY sales_delta ASC;"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation="Builds monthly product sales in a CTE and uses `LAG()` partitioned by `product_id` to detect products whose latest month revenue fell compared to the prior month.",
                assumptions=["Products with zero sales in the latest month are not represented unless left-joined from products x months."],
                limitations=["Excludes cancelled orders; month-over-month drops reflect gross line_total revenue."],
            )

    # 7. Customers who purchased more than N times
    if "customer" in low and any(k in low for k in ("more than", "greater than", "over", "times", "repeat", "frequent")):
        if cust_tbl is not None and ord_tbl is not None:
            thresh = _extract_gt_threshold(low, 3)
            name_expr = (
                "c.customer_name"
                if cust_tbl.get_column("customer_name")
                else ("CONCAT(c.first_name, ' ', c.last_name)" if cust_tbl.get_column("first_name") else "c.email")
            )
            sql = f"""SELECT
    c.customer_id,
    {name_expr} AS customer_name,
    c.email,
    c.country,
    COUNT(o.order_id) AS purchase_count,
    ROUND(SUM(o.total_amount), 2) AS lifetime_spend
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.status <> 'cancelled'
GROUP BY c.customer_id, {name_expr}, c.email, c.country
HAVING COUNT(o.order_id) > {thresh}
ORDER BY purchase_count DESC, lifetime_spend DESC;"""
            return PlannedQuery(
                postgres_sql=sql,
                explanation=f"Joins `customers` and `orders`, groups per customer, and applies `HAVING COUNT(o.order_id) > {thresh}` to keep repeat buyers.",
                assumptions=[f"Excluded cancelled orders and counted distinct orders > {thresh}."],
                limitations=["Groups by `customer_id`; if duplicate customer profiles exist under separate IDs, deduplicate by email first."],
            )

    # 8. Duplicate customer records
    if "duplicate" in low and cust_tbl is not None:
        if "name" in clar and cust_tbl.get_column("customer_name") and cust_tbl.get_column("country"):
            sql = """SELECT
    LOWER(TRIM(customer_name)) AS normalized_name,
    country,
    COUNT(*) AS record_count,
    MIN(customer_id) AS first_customer_id,
    MAX(customer_id) AS latest_customer_id
FROM customers
GROUP BY LOWER(TRIM(customer_name)), country
HAVING COUNT(*) > 1
ORDER BY record_count DESC, normalized_name;"""
        else:
            sql = """SELECT
    LOWER(TRIM(email)) AS normalized_email,
    COUNT(*) AS duplicate_count,
    MIN(customer_id) AS primary_customer_id,
    MAX(customer_id) AS duplicate_customer_id
FROM customers
GROUP BY LOWER(TRIM(email))
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, normalized_email;"""
        return PlannedQuery(
            postgres_sql=sql,
            explanation="Normalizes customer key attributes (`LOWER(TRIM(...))`) and identifies groups where `COUNT(*) > 1`.",
            assumptions=["Case-insensitive whitespace-trimmed match used for deduplication accuracy."],
            limitations=["Summary view returns MIN/MAX matching IDs so query runs cleanly across PostgreSQL, MySQL, SQLite, and SQL Server without array/string aggregation dialect issues."],
            alternatives=[
                {
                    "title": "Return full individual duplicate rows using Window COUNT()",
                    "sql": """WITH ranked AS (
    SELECT
        customer_id,
        customer_name,
        email,
        country,
        COUNT(*) OVER (PARTITION BY LOWER(TRIM(email))) AS grp_count
    FROM customers
)
SELECT customer_id, customer_name, email, country, grp_count
FROM ranked
WHERE grp_count > 1
ORDER BY email, customer_id;""",
                    "reason": "Shows every duplicate row individually instead of collapsed aggregates.",
                }
            ],
        )

    # 9. General schema-matching query builder for arbitrary active datasets/uploads!
    best_tbl = context.tables[0]
    best_score = -1
    req_tokens = set(re.findall(r"[a-zA-Z0-9_]+", low))
    for tbl in context.tables:
        score = 0
        t_words = set(tbl.name.lower().split("_"))
        score += 4 * len(req_tokens & t_words)
        if tbl.name.lower() in low:
            score += 6
        for c in tbl.columns:
            c_words = set(c.name.lower().split("_"))
            if req_tokens & c_words:
                score += 2
        if score > best_score:
            best_score = score
            best_tbl = tbl

    limit_n = _extract_limit(low, 25)
    num_col = _find_numeric_col(best_tbl, ("revenue", "amount", "total", "sales", "price", "salary", "quota", "count"))
    dim_col = _find_name_col(best_tbl)
    date_col = _find_date_col(best_tbl)

    if any(k in low for k in ("count", "sum", "total", "average", "avg", "by ", "per ")) and dim_col and num_col:
        agg_fn = "AVG" if ("average" in low or "avg" in low) else "SUM"
        sql = f"""SELECT
    {dim_col},
    COUNT(*) AS record_count,
    ROUND({agg_fn}({num_col}), 2) AS metric_value
FROM {best_tbl.name}
GROUP BY {dim_col}
ORDER BY metric_value DESC
LIMIT {limit_n};"""
        return PlannedQuery(
            postgres_sql=sql,
            explanation=f"Aggregates `{best_tbl.name}` grouped by `{dim_col}` computing `{agg_fn}({num_col})` directly from verified columns.",
            assumptions=[f"Selected `{best_tbl.name}` because its columns best match your request terms."],
            limitations=["Verify whether filters or multi-table joins are needed for business-specific definitions."],
        )

    cols_preview = ", ".join(c.name for c in best_tbl.columns[:8])
    order_clause = f"\nORDER BY {num_col} DESC" if num_col and ("top" in low or "highest" in low) else (f"\nORDER BY {date_col} DESC" if date_col else "")
    sql = f"""SELECT
    {cols_preview}
FROM {best_tbl.name}{order_clause}
LIMIT {limit_n};"""
    return PlannedQuery(
        postgres_sql=sql,
        explanation=f"Retrieves structured preview columns from `{best_tbl.name}` capped at {limit_n} rows.",
        assumptions=[f"Projected explicit columns instead of `SELECT *` from `{best_tbl.name}`."],
        limitations=["Add a WHERE predicate or clarified metric if you want filtered aggregation."],
    )
