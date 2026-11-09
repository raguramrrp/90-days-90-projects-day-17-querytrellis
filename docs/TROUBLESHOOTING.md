# Troubleshooting — QueryTrellis

## Common Windows & PostgreSQL Issues

### 1. `Authentication failed for user 'postgres'`
- **Cause:** Local PostgreSQL 14–18 requires a password (`scram-sha-256` or `md5`), and `.env` still has `PGPASSWORD=` blank.
- **Fix:** Edit `.env` with your PostgreSQL password (`PGPASSWORD=your_password`), or enter the password inside **Settings -> PostgreSQL Connection** in the UI. Alternatively, use the isolated project cluster (`scripts\local_pg_cluster.py start --port 55432`) which uses local loopback `trust` authentication on `127.0.0.1`.

### 2. `Database 'querytrellis_sample' does not exist`
- **Cause:** Sample database has not been created and populated yet.
- **Fix:**
  ```powershell
  .\.venv\Scripts\python.exe scripts\setup_sample_db.py
  ```

### 3. `Cannot reach PostgreSQL at localhost:5432`
- **Cause:** The Windows PostgreSQL service is stopped or running on a non-default port (e.g., `5433`).
- **Fix:** Start the PostgreSQL service in Windows Services (`postgresql-x64-18`), update `PGPORT` in `.env` / Settings, or run `scripts\local_pg_cluster.py start --port 55432`.

### 4. `Query exceeded the configured statement timeout`
- **Cause:** An unindexed cross-table query took longer than `QT_DEFAULT_STATEMENT_TIMEOUT_MS` (default `5000` ms).
- **Fix:** Increase **Default Statement Timeout (ms)** under **Settings -> Safety & Execution Guardrails**, add selective `WHERE` / `LIMIT` clauses, or use `EXPLAIN (Estimate Only)` mode first.

### 5. `Blocked non-read-only or restricted operation`
- **Cause:** Attempted `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `SELECT ... INTO`, `FOR UPDATE`, or multiple semicolon-separated statements.
- **Fix:** QueryTrellis intentionally restricts execution and `EXPLAIN ANALYZE` to single read-only `SELECT` statements. Remove mutation/DDL statements or split multi-statement batches.

### 6. `ModuleNotFoundError: No module named 'src'`
- **Cause:** Running Python directly without project root on `PYTHONPATH` or outside `.venv`.
- **Fix:** Launch via `.\run.bat` / `.\test.bat`, or set `$env:PYTHONPATH = "."` in PowerShell before invoking `.venv\Scripts\python.exe`.
