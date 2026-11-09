# Development Notes — QueryTrellis

## Key Engineering Decisions

### 1. AST Validation vs. Naive String Matching
Checking `sql.strip().upper().startswith("SELECT")` is trivially bypassed by CTE write statements (`WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d`), multi-statement injection (`SELECT 1; DROP TABLE orders;`), `SELECT ... INTO`, or row locking (`SELECT * FROM orders FOR UPDATE`). QueryTrellis parses SQL with SQLGlot (`dialect="postgres"`), enforces a single parsed statement, walks the full AST rejecting any mutation/DDL/DCL/lock/admin-function node, and pairs that with PostgreSQL's own `SET TRANSACTION READ ONLY` and `SET LOCAL statement_timeout` enforcement.

### 2. SQLite Separation for Metadata
Application operational metadata (query history, saved benchmarks, comparison snapshots, connection profiles without passwords) is stored in a dedicated local SQLite WAL file (`data/querytrellis_meta.db`). This ensures inspecting a target PostgreSQL database never pollutes the analyzed schema with tool tables and keeps QueryTrellis usable even while disconnected.

### 3. Exclusive Node Self-Time Semantics
In PostgreSQL `EXPLAIN (ANALYZE, FORMAT JSON)`, `Actual Total Time` represents the average millisecond duration *per loop*, inclusive of descendant nodes. `src/explain/plan_parser.py` computes `inclusive_time_ms = actual_total_time * actual_loops` and derives `self_time_ms` by subtracting direct non-`InitPlan` child inclusive times (clamped at `0.0` to handle parallel worker rounding differences cleanly).

### 4. Client Duration vs. PostgreSQL Execution Time
Benchmarks report both client wall-clock duration (Python + `psycopg` + IPC/TCP round trip) and PostgreSQL server `Execution Time` / `Planning Time`. Using `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` per benchmark iteration avoids distorting results through UI row truncation (`LIMIT 500`) while exposing buffer cache warming across iterations (`Shared Hit Blocks` vs. `Shared Read Blocks`).

### 5. Non-Redundant Index Advisor
QueryTrellis reads exact ordered `key_columns`, `include_columns`, and partial `indpred` expressions from `pg_index` (`indnkeyatts`) rather than parsing index text loosely. If an existing B-tree index already leads with the candidate column(s), QueryTrellis avoids recommending a duplicate index.
