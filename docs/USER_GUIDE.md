# User Guide — QueryTrellis

## 1. Connect to PostgreSQL (`Settings`)

1. Open **Settings** from the left sidebar.
2. Enter your PostgreSQL **Host**, **Port**, **Database Name**, **Username**, and **Password**.
3. Click **Test Connection** to verify server connectivity and view the PostgreSQL version.
4. Click **Connect**. You can optionally save the connection profile (passwords are never persisted to SQLite).
5. Use the **Schema & Index Browser** tab to explore tables, estimated row counts, disk footprints, existing indexes, and foreign keys, or adjust `statement_timeout` and `max_rows` under **Safety & Execution Guardrails**.

## 2. Edit, Validate, Execute & Analyze SQL (`Query Editor`)

- **Sample Query Library:** Select any built-in query (e.g., non-indexed FK filter, 4-table JOIN, CTE + `DENSE_RANK()`, correlated subquery vs. CTE rewrite) and click **Load Example** (or **Load Optimization Pair**).
- **Validate:** Checks single-statement PostgreSQL syntax and verifies read-only safety offline.
- **Format SQL:** Pretty-prints SQL via SQLGlot.
- **Execute:** Runs the validated `SELECT` inside `SET TRANSACTION READ ONLY` with timeout and row-cap protection, displaying results and CSV export.
- **Analyze Query:** Runs anti-pattern detection, index recommendation, and either `EXPLAIN (ANALYZE, BUFFERS)` or estimate-only `EXPLAIN`.

## 3. Inspect Execution Plans (`Explain Plan`)

- View KPI metrics (PG Execution Time, Planning Time, Estimated Cost, Actual vs. Estimated Root Rows, Shared Buffer Hits/Reads).
- Switch across **Execution Plan Tree**, **Node Metrics Table**, **Visual Charts** (exclusive self-time breakdown and estimated vs. actual rows), and the **Node Inspector**.
- Review **Plan Diagnostics & Bottleneck Highlights** for nuanced interpretation (including when sequential scans on small tables are already optimal).

## 4. Review Anti-Patterns & Index Suggestions (`Recommendations`)

- Filter detected SQL anti-patterns by severity (`High`, `Medium`, `Low`) and review both performance risks and when each pattern is acceptable.
- Inspect advisory index DDL statements (`Single-Column B-tree`, `Composite B-tree`, `Covering (INCLUDE)`, `Partial B-tree`) along with write/storage overhead notes. Copy individual statements or download `.sql` files to apply manually if desired.

## 5. Benchmark & Compare Optimizations (`Benchmark Lab`)

- **Single Query Benchmark:** Configure repeat count (2–20) and optional warmup run to compare Run 1 cold/warm cache effects alongside Min, Median, Mean, Max, and P95 timings.
- **Before & After Comparison:** Compare an Original Query (A) against an Optimized Query (B). QueryTrellis validates row count equivalence, computes percentage timing and cost deltas, tracks plan node/index changes, and states an evidence-based verdict (`Improved`, `Regressed`, `No Significant Change`, `Row Count Mismatch`, or `Inconclusive`).

## 6. History & Optimization Reports (`Query History` & `Reports`)

- Browse, search, and reopen past analyses from the local SQLite history log.
- Export complete HTML, JSON, Plan Nodes CSV, and Benchmark CSV reports from **Reports**.
