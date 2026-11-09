# QueryTrellis UI Screenshots

## QueryTrellis Studio (Next.js 15 Light-First Editorial Workstation)

Captured locally from the live running Next.js + FastAPI stack (`frontend/` + `src/api/main.py`) on a `1440x900` viewport connected to the offline **Enterprise HR & Sales Demo** (`duckdb` sandbox, 7 tables, `PostgreSQL` target dialect):

| File | Workspace / Route | Highlights Shown |
|---|---|---|
| [`studio_query_studio.png`](studio_query_studio.png) | Query Studio (`/`) | Horizontal top masthead navigation, expandable inline schema catalog pills, natural language workbench, `#171B1A` Monaco SQL preview, AST verification status, and prompt gallery |
| [`studio_sql_ide.png`](studio_sql_ide.png) | SQL IDE (`/sql-editor`) | Collapsible schema explorer tree, `#171B1A` Monaco SQL editor, SQLGlot AST validation/formatting, dialect converter bar, and multi-tab execution & clause results |
| [`studio_debugging.png`](studio_debugging.png) | Debugger (`/debugging`) | Sample fault scenario presets, SQL editor under diagnosis, runtime trace input, and AST fix verification workflow |
| [`studio_optimizer.png`](studio_optimizer.png) | Optimizer (`/optimizer`) | Three-tier analysis header (Tier 1 Static AST, Tier 2 Planner estimate, Tier 3 Consent-locked measured timing), optimization presets, and query analyzer |
| [`studio_academy.png`](studio_academy.png) | SQL Academy (`/academy`) | 21-lesson interactive curriculum syllabus, mental-model callout, step-by-step DuckDB `StageTraceViewer` (`FROM & JOIN` -> `SELECT` -> `Final Query Result`), and live exercise workspace |
| [`studio_databases.png`](studio_databases.png) | Databases (`/database-manager`) | Inspect-before-accept `.sql`/`.dump`/`.csv`/`.xlsx`/`.json` uploader, bundled multi-format sample datasets, live DB connector tab, and active schema browser |
| [`studio_engine_api.png`](studio_engine_api.png) | Engine API (`/ai-settings`) | Top-aligned Save Configuration action, offline **Deterministic Schema AST Engine** mode card, opt-in **External Cloud API Gateway**, and compiler fallback disclosure |

---

## Preserved Legacy Streamlit Performance Workbench (`app/main.py`)

Captured locally from the live running Streamlit application connected to PostgreSQL 18.6 (`127.0.0.1:55432`) with the 281,525-row `querytrellis_sample` database loaded (`1440x1040` viewport):

| File | Page / View | Highlights Shown |
|---|---|---|
| [`overview_dashboard.png`](overview_dashboard.png) | Overview Dashboard | Live PostgreSQL telemetry, table & index footprint (`pg_stat_user_tables`), recent analyses, anti-pattern counts |
| [`query_editor.png`](query_editor.png) | SQL Query Editor | Sample query library, SQL input editor, safety notice, execution summary metrics, quick navigation |
| [`explain_plan.png`](explain_plan.png) | Execution Plan Analyzer (Tree) | `EXPLAIN (ANALYZE, BUFFERS)` execution tree, node metrics, buffer stats, and bottleneck diagnostics |
| [`explain_plan_charts.png`](explain_plan_charts.png) | Execution Plan Analyzer (Visual Charts) | Exclusive node self-time Plotly chart and Estimated vs. Actual row count comparison |
| [`recommendations.png`](recommendations.png) | Recommendations (Anti-Patterns) | Severity-filtered AST findings with SQL fragments, impact explanation, acceptable contexts, and fixes |
| [`recommendations_indexes.png`](recommendations_indexes.png) | Recommendations (Index Advisor) | Non-redundant advisory `CREATE INDEX` DDL with `pg_catalog` duplicate check and overhead trade-offs |
| [`benchmark_lab.png`](benchmark_lab.png) | Benchmark Lab (Single Query) | Repeat configuration, client vs. PostgreSQL server timings, per-run table, and duration profile chart |
| [`benchmark_comparison.png`](benchmark_comparison.png) | Benchmark Lab (Before & After Comparison) | Paired baseline vs. candidate SQL editor, percentage speedup verdict, and row-count equivalence check |
| [`query_history.png`](query_history.png) | Query Analysis History | Filterable SQLite history table and one-click reload into Editor, Explain Plan, Recommendations, or Reports |
| [`reports.png`](reports.png) | Optimization Reports | Downloadable HTML, JSON, Plan Nodes CSV, Benchmark CSV buttons, and live HTML report preview |
| [`settings.png`](settings.png) | Settings (PostgreSQL Connection) | Host/Port/DB/User/Password form (password kept in memory only), profiles, active server telemetry |
| [`settings_schema.png`](settings_schema.png) | Settings (Schema & Index Browser) | Interactive inspector for columns, data types, existing B-tree/unique indexes, `idx_scan`, and foreign keys |
