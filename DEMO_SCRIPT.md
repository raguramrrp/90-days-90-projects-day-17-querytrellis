# QueryTrellis — 90-Second Demo Script

## Objective
Demonstrate a complete PostgreSQL query performance diagnosis and before-and-after optimization workflow on the 281,525-row synthetic e-commerce database (`querytrellis_sample`).

## Pre-Demo Checklist
1. Ensure PostgreSQL is running and seeded (`scripts/setup_sample_db.py`).
2. Launch QueryTrellis (`.\run.bat`) and open `http://127.0.0.1:8501`.

## Step-by-Step Sequence (60–120 Seconds)

1. **[0:00–0:15] Overview & Live Telemetry**
   - Show **Overview Dashboard**: point out `Connected` status, PostgreSQL version, 8 sample tables (`281,525` total rows), and `pg_stat_user_tables` scan metrics.
2. **[0:15–0:35] Safety Guardrails in Action (`Query Editor`)**
   - Paste `WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d` and click **Validate** -> show AST validation blocking the write inside a CTE immediately before reaching PostgreSQL.
   - Select **Sample #1 (`Non-Indexed Filter: orders.customer_id`)**, click **Load Example**, then click **Analyze Query**.
3. **[0:35–0:55] Execution Plan Inspection (`Explain Plan`)**
   - Open **Explain Plan**: highlight the `Seq Scan on orders` node, filter removal count (`~54,995 rows discarded`), Estimated vs. Actual rows chart, and node self-time breakdown.
4. **[0:55–1:10] Anti-Patterns & Index Advisor (`Recommendations`)**
   - Open **Recommendations**: show `CREATE INDEX idx_orders_customer_id ON orders(customer_id);` (plus Covering `INCLUDE` option), noting write/storage trade-offs and that QueryTrellis never applies DDL automatically.
5. **[1:10–1:35] Before-and-After Comparison (`Benchmark Lab`)**
   - Open **Benchmark Lab -> Before & After Optimization Comparison**.
   - Load **Sample #7 (`Correlated Subquery vs. CTE LEFT JOIN`)** and click **Analyze & Benchmark Both**.
   - Highlight the verified speedup, `Row Count Mismatch` safety check (matched!), plan node transformation (`SubPlan` removed -> `HashAggregate` + `Hash Left Join`), and resolved anti-pattern (`AP006`).
6. **[1:35–1:50] History & Sanitized Report Export (`Query History` & `Reports`)**
   - Show **Query History** persistence in SQLite and preview/download the self-contained HTML and JSON reports on **Reports** (confirming zero credentials are exposed).
