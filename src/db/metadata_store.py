"""Local SQLite metadata store for QueryTrellis history, benchmarks, comparisons, and preferences.

Strictly separate from the target PostgreSQL database under analysis.
Never stores plain-text PostgreSQL passwords.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class MetadataStore:
    """SQLite persistence layer for QueryTrellis operational metadata."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if str(self.db_path) != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS connection_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    database_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    sslmode TEXT NOT NULL DEFAULT 'prefer',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS query_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    schema_name TEXT NOT NULL DEFAULT 'public',
                    sql_text TEXT NOT NULL,
                    sql_hash TEXT NOT NULL,
                    formatted_sql TEXT,
                    status TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    client_duration_ms REAL,
                    pg_planning_ms REAL,
                    pg_execution_ms REAL,
                    rows_returned INTEGER,
                    total_cost REAL,
                    plan_json TEXT,
                    summary_json TEXT,
                    antipatterns_json TEXT,
                    recommendations_json TEXT,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_query_analyses_created_at
                    ON query_analyses(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_query_analyses_hash
                    ON query_analyses(sql_hash);

                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    label TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    sql_text TEXT NOT NULL,
                    sql_hash TEXT NOT NULL,
                    repeat_count INTEGER NOT NULL,
                    warmup_used INTEGER NOT NULL DEFAULT 0,
                    min_ms REAL NOT NULL,
                    max_ms REAL NOT NULL,
                    mean_ms REAL NOT NULL,
                    median_ms REAL NOT NULL,
                    p95_ms REAL NOT NULL,
                    pg_exec_median_ms REAL,
                    iterations_json TEXT NOT NULL,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS query_comparisons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    baseline_sql TEXT NOT NULL,
                    optimized_sql TEXT NOT NULL,
                    baseline_analysis_id INTEGER,
                    optimized_analysis_id INTEGER,
                    baseline_benchmark_id INTEGER,
                    optimized_benchmark_id INTEGER,
                    comparison_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    format TEXT NOT NULL,
                    file_path TEXT,
                    analysis_id INTEGER,
                    comparison_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS app_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # Connection profiles (NO PASSWORDS STORED)
    # ------------------------------------------------------------------
    def save_connection_profile(
        self,
        name: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        sslmode: str = "prefer",
        is_default: bool = False,
    ) -> int:
        now = _utc_now_iso()
        with self._connect() as conn:
            if is_default:
                conn.execute("UPDATE connection_profiles SET is_default = 0")
            cur = conn.execute(
                """
                INSERT INTO connection_profiles
                    (name, host, port, database_name, username, sslmode, is_default, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    host = excluded.host,
                    port = excluded.port,
                    database_name = excluded.database_name,
                    username = excluded.username,
                    sslmode = excluded.sslmode,
                    is_default = excluded.is_default,
                    updated_at = excluded.updated_at
                """,
                (name.strip(), host.strip(), int(port), database_name.strip(), username.strip(), sslmode, int(is_default), now),
            )
            return int(cur.lastrowid or 0)

    def list_connection_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, host, port, database_name, username, sslmode, is_default, updated_at "
                "FROM connection_profiles ORDER BY is_default DESC, updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_connection_profile(self, name: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM connection_profiles WHERE name = ?", (name,))

    # ------------------------------------------------------------------
    # Query analyses
    # ------------------------------------------------------------------
    def save_analysis(
        self,
        *,
        database_name: str,
        sql_text: str,
        sql_hash: str,
        status: str,
        execution_mode: str,
        schema_name: str = "public",
        formatted_sql: str | None = None,
        client_duration_ms: float | None = None,
        pg_planning_ms: float | None = None,
        pg_execution_ms: float | None = None,
        rows_returned: int | None = None,
        total_cost: float | None = None,
        plan_json: Any = None,
        summary_json: Any = None,
        antipatterns_json: Any = None,
        recommendations_json: Any = None,
        error_message: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO query_analyses (
                    created_at, database_name, schema_name, sql_text, sql_hash, formatted_sql,
                    status, execution_mode, client_duration_ms, pg_planning_ms, pg_execution_ms,
                    rows_returned, total_cost, plan_json, summary_json, antipatterns_json,
                    recommendations_json, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    database_name,
                    schema_name,
                    sql_text,
                    sql_hash,
                    formatted_sql,
                    status,
                    execution_mode,
                    client_duration_ms,
                    pg_planning_ms,
                    pg_execution_ms,
                    rows_returned,
                    total_cost,
                    json.dumps(plan_json) if plan_json is not None else None,
                    json.dumps(summary_json) if summary_json is not None else None,
                    json.dumps(antipatterns_json) if antipatterns_json is not None else None,
                    json.dumps(recommendations_json) if recommendations_json is not None else None,
                    error_message,
                ),
            )
            return int(cur.lastrowid or 0)

    def _hydrate_analysis(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        d = dict(row)
        for field_name in ("plan_json", "summary_json", "antipatterns_json", "recommendations_json"):
            raw = d.get(field_name)
            if raw:
                try:
                    d[field_name] = json.loads(raw)
                except json.JSONDecodeError:
                    d[field_name] = None
        return d

    def get_analysis(self, analysis_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM query_analyses WHERE id = ?", (analysis_id,)).fetchone()
            return self._hydrate_analysis(row)

    def list_analyses(
        self,
        *,
        limit: int = 100,
        database_filter: str | None = None,
        status_filter: str | None = None,
        search_text: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if database_filter and database_filter != "All":
            clauses.append("database_name = ?")
            params.append(database_filter)
        if status_filter and status_filter != "All":
            clauses.append("status = ?")
            params.append(status_filter)
        if search_text and search_text.strip():
            clauses.append("LOWER(sql_text) LIKE ?")
            params.append(f"%{search_text.strip().lower()}%")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM query_analyses {where_sql} ORDER BY id DESC LIMIT ?",
                params,
            ).fetchall()
            return [h for r in rows if (h := self._hydrate_analysis(r)) is not None]

    # ------------------------------------------------------------------
    # Benchmark runs
    # ------------------------------------------------------------------
    def save_benchmark(
        self,
        *,
        label: str,
        database_name: str,
        sql_text: str,
        sql_hash: str,
        repeat_count: int,
        warmup_used: bool,
        min_ms: float,
        max_ms: float,
        mean_ms: float,
        median_ms: float,
        p95_ms: float,
        pg_exec_median_ms: float | None,
        iterations: list[dict[str, Any]],
        notes: str = "",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO benchmark_runs (
                    created_at, label, database_name, sql_text, sql_hash, repeat_count,
                    warmup_used, min_ms, max_ms, mean_ms, median_ms, p95_ms,
                    pg_exec_median_ms, iterations_json, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    label,
                    database_name,
                    sql_text,
                    sql_hash,
                    int(repeat_count),
                    int(warmup_used),
                    float(min_ms),
                    float(max_ms),
                    float(mean_ms),
                    float(median_ms),
                    float(p95_ms),
                    pg_exec_median_ms,
                    json.dumps(iterations),
                    notes,
                ),
            )
            return int(cur.lastrowid or 0)

    def list_benchmarks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["iterations"] = json.loads(d.pop("iterations_json"))
                except Exception:
                    d["iterations"] = []
                result.append(d)
            return result

    # ------------------------------------------------------------------
    # Comparisons
    # ------------------------------------------------------------------
    def save_comparison(
        self,
        *,
        title: str,
        database_name: str,
        baseline_sql: str,
        optimized_sql: str,
        comparison_data: dict[str, Any],
        baseline_analysis_id: int | None = None,
        optimized_analysis_id: int | None = None,
        baseline_benchmark_id: int | None = None,
        optimized_benchmark_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO query_comparisons (
                    created_at, title, database_name, baseline_sql, optimized_sql,
                    baseline_analysis_id, optimized_analysis_id,
                    baseline_benchmark_id, optimized_benchmark_id, comparison_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    title,
                    database_name,
                    baseline_sql,
                    optimized_sql,
                    baseline_analysis_id,
                    optimized_analysis_id,
                    baseline_benchmark_id,
                    optimized_benchmark_id,
                    json.dumps(comparison_data),
                ),
            )
            return int(cur.lastrowid or 0)

    def list_comparisons(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM query_comparisons ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["comparison"] = json.loads(d.pop("comparison_json"))
                except Exception:
                    d["comparison"] = {}
                result.append(d)
            return result

    # ------------------------------------------------------------------
    # Reports & Preferences
    # ------------------------------------------------------------------
    def save_report_record(
        self,
        *,
        title: str,
        database_name: str,
        fmt: str,
        file_path: str | None = None,
        analysis_id: int | None = None,
        comparison_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO report_history (
                    created_at, title, database_name, format, file_path, analysis_id, comparison_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_utc_now_iso(), title, database_name, fmt, file_path, analysis_id, comparison_id),
            )
            return int(cur.lastrowid or 0)

    def list_reports(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM report_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM app_preferences WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def set_preference(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_preferences (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, str(value), _utc_now_iso()),
            )

    def get_overview_stats(self) -> dict[str, Any]:
        """Compute strictly real aggregate metrics from stored records (never fabricated)."""
        with self._connect() as conn:
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_analyses,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successful_analyses,
                    AVG(CASE WHEN status = 'success' THEN COALESCE(pg_execution_ms, client_duration_ms) END) AS avg_exec_ms
                FROM query_analyses
                """
            ).fetchone()
            bench_count = conn.execute("SELECT COUNT(*) AS cnt FROM benchmark_runs").fetchone()
            comp_count = conn.execute("SELECT COUNT(*) AS cnt FROM query_comparisons").fetchone()

            recent_rows = conn.execute(
                "SELECT id, created_at, database_name, status, execution_mode, "
                "client_duration_ms, pg_execution_ms, rows_returned, total_cost, antipatterns_json, sql_text "
                "FROM query_analyses ORDER BY id DESC LIMIT 10"
            ).fetchall()

            all_ap_rows = conn.execute(
                "SELECT antipatterns_json FROM query_analyses WHERE antipatterns_json IS NOT NULL"
            ).fetchall()

        issue_counts: dict[str, int] = {}
        for row in all_ap_rows:
            try:
                items = json.loads(row["antipatterns_json"])
                for item in items:
                    name = item.get("issue_name", "Unknown")
                    issue_counts[name] = issue_counts.get(name, 0) + 1
            except Exception:
                continue

        common_issues = [
            {"issue_name": k, "count": v}
            for k, v in sorted(issue_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

        return {
            "total_analyses": int(counts["total_analyses"] or 0) if counts else 0,
            "successful_analyses": int(counts["successful_analyses"] or 0) if counts else 0,
            "avg_execution_ms": (
                round(float(counts["avg_exec_ms"]), 3)
                if counts and counts["avg_exec_ms"] is not None
                else None
            ),
            "total_benchmarks": int(bench_count["cnt"] or 0) if bench_count else 0,
            "total_comparisons": int(comp_count["cnt"] or 0) if comp_count else 0,
            "recent_analyses": [dict(r) for r in recent_rows],
            "common_issues": common_issues,
        }
