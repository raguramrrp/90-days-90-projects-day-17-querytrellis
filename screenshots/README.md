# QueryTrellis UI Screenshots

All screenshots below were captured locally from the live running Streamlit application (`app/main.py`) connected to PostgreSQL 18.6 (`127.0.0.1:55432`) with the 281,525-row `querytrellis_sample` database loaded (`1440x1040` viewport).

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
