# Testing Guide — QueryTrellis

## Test Suite Architecture

The test suite under `tests/` separates fast offline unit tests (with mocked connections where appropriate) from live PostgreSQL integration tests:

| Test File | Scope |
|---|---|
| `tests/test_parser_validator.py` | SQLGlot parsing, read-only AST whitelist, CTE write rejection, `SELECT INTO` & `FOR UPDATE` rejection, multi-statement rejection, malformed SQL handling, SQL formatting |
| `tests/test_antipattern_detector.py` | All 15 SQL anti-pattern rules (`AP001`–`AP015`), non-flagging of `COUNT(*)`, metadata-assisted implicit type coercion checks |
| `tests/test_safe_executor.py` | Mocked `psycopg` verification of `SET TRANSACTION READ ONLY`, `SET LOCAL statement_timeout`, server-cursor `max_rows` truncation, and `EXPLAIN` execution |
| `tests/test_plan_parser_analyzer.py` | `EXPLAIN (FORMAT JSON)` tree construction, inclusive/self-time math, estimate-only `Unavailable` preservation, disk sort, cardinality misestimation, small-table Seq Scan nuance |
| `tests/test_index_recommender.py` | Single-column, composite ESR, covering `INCLUDE`, partial indexes, duplicate avoidance, small-table suppression, non-sargable filter guard |
| `tests/test_benchmark_comparator.py` | Min/max/mean/median/p95/stdev stats, mid-benchmark interruption handling, before/after comparison verdicts (including row-count mismatch detection) |
| `tests/test_report_generator.py` | HTML, JSON, benchmark CSV, and plan-node CSV exports + strict verification that passwords never appear |
| `tests/test_connection_and_store.py` | PostgreSQL error translation, unreachable host handling, SQLite CRUD without password storage |
| `tests/test_workbench_service.py` | Sample query library validation, offline & mocked orchestration workflows |
| `tests/test_postgres_integration.py` | End-to-end live PostgreSQL integration tests (`@pytest.mark.integration`) |

## Execution Commands (Windows PowerShell)

```powershell
# Run full suite (integration tests skip cleanly if PostgreSQL is unreachable)
.\test.bat

# Run offline unit tests only
.\.venv\Scripts\python.exe -m pytest -v tests/ -m "not integration"

# Run full suite including live PostgreSQL integration tests against local port 55432
$env:QT_TEST_PG_HOST="127.0.0.1"
$env:QT_TEST_PG_PORT="55432"
$env:QT_TEST_PG_USER="postgres"
$env:QT_TEST_PG_DB="querytrellis_sample"
$env:QT_TEST_PG_PASSWORD=""
.\.venv\Scripts\python.exe -m pytest -v tests/ --cov=src --cov-report=term-missing
```
