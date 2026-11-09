"""Safe, read-only PostgreSQL query and EXPLAIN execution layer."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import psycopg

from src.db.connection_manager import translate_pg_error
from src.sql_analysis.parser_validator import ValidationResult, validate_read_only_sql


@dataclass(slots=True)
class QueryExecutionResult:
    """Result of executing a validated read-only SQL statement."""

    success: bool
    validation: ValidationResult
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    rows_returned: int = 0
    was_truncated: bool = False
    max_rows_applied: int = 500
    client_duration_ms: float = 0.0
    error_message: str = ""


@dataclass(slots=True)
class ExplainExecutionResult:
    """Raw PostgreSQL EXPLAIN (FORMAT JSON) execution output."""

    success: bool
    validation: ValidationResult
    analyzed: bool
    buffers_enabled: bool
    raw_plan_json: list[dict[str, Any]] | dict[str, Any] | None = None
    client_duration_ms: float = 0.0
    error_message: str = ""


def _clamp_timeout(timeout_ms: int) -> int:
    return max(100, min(120_000, int(timeout_ms)))


def _clamp_max_rows(max_rows: int) -> int:
    return max(1, min(10_000, int(max_rows)))


def execute_safe_query(
    conn: psycopg.Connection[Any],
    sql: str,
    *,
    timeout_ms: int = 5000,
    max_rows: int = 500,
) -> QueryExecutionResult:
    """Validate and execute a single read-only SELECT query inside a read-only transaction."""
    validation = validate_read_only_sql(sql)
    if not validation.is_valid or not validation.is_read_only:
        return QueryExecutionResult(
            success=False,
            validation=validation,
            max_rows_applied=max_rows,
            error_message=validation.error_message or "Query failed read-only validation.",
        )

    safe_timeout = _clamp_timeout(timeout_ms)
    safe_limit = _clamp_max_rows(max_rows)
    clean_sql = validation.clean_sql

    t0 = time.perf_counter()
    try:
        # Ensure clean starting transaction state
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()

        with conn.transaction():
            with conn.cursor() as guard_cur:
                guard_cur.execute("SET TRANSACTION READ ONLY")
                guard_cur.execute(f"SET LOCAL statement_timeout = {safe_timeout}")

            # Server-side cursor caps transferred rows so huge tables cannot OOM the UI
            with conn.cursor(name="qt_safe_preview") as scur:
                scur.itersize = safe_limit + 1
                scur.execute(clean_sql)
                columns = [desc.name for desc in (scur.description or [])]
                fetched = scur.fetchmany(safe_limit + 1)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        was_truncated = len(fetched) > safe_limit
        rows = list(fetched[:safe_limit])
        return QueryExecutionResult(
            success=True,
            validation=validation,
            columns=columns,
            rows=rows,
            rows_returned=len(rows),
            was_truncated=was_truncated,
            max_rows_applied=safe_limit,
            client_duration_ms=round(elapsed_ms, 3),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        try:
            conn.rollback()
        except Exception:
            pass
        return QueryExecutionResult(
            success=False,
            validation=validation,
            max_rows_applied=safe_limit,
            client_duration_ms=round(elapsed_ms, 3),
            error_message=translate_pg_error(exc),
        )


def run_explain_plan(
    conn: psycopg.Connection[Any],
    sql: str,
    *,
    analyze: bool = True,
    buffers: bool = True,
    timeout_ms: int = 5000,
) -> ExplainExecutionResult:
    """Run EXPLAIN or EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) for a validated read-only SQL query."""
    validation = validate_read_only_sql(sql)
    if not validation.is_valid or not validation.is_read_only:
        return ExplainExecutionResult(
            success=False,
            validation=validation,
            analyzed=analyze,
            buffers_enabled=buffers and analyze,
            error_message=validation.error_message or "Query failed read-only validation.",
        )

    safe_timeout = _clamp_timeout(timeout_ms)
    clean_sql = validation.clean_sql
    use_buffers = bool(buffers and analyze)

    options = ["FORMAT JSON"]
    if analyze:
        options.insert(0, "ANALYZE")
        if use_buffers:
            options.insert(1, "BUFFERS")

    explain_sql = f"EXPLAIN ({', '.join(options)}) {clean_sql}"

    t0 = time.perf_counter()
    try:
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()

        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(f"SET LOCAL statement_timeout = {safe_timeout}")
                cur.execute(explain_sql)
                row = cur.fetchone()
                raw_json = row[0] if row else None
        # Always rollback cleanly after EXPLAIN ANALYZE
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return ExplainExecutionResult(
            success=True,
            validation=validation,
            analyzed=analyze,
            buffers_enabled=use_buffers,
            raw_plan_json=raw_json,
            client_duration_ms=round(elapsed_ms, 3),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        try:
            conn.rollback()
        except Exception:
            pass
        return ExplainExecutionResult(
            success=False,
            validation=validation,
            analyzed=analyze,
            buffers_enabled=use_buffers,
            client_duration_ms=round(elapsed_ms, 3),
            error_message=translate_pg_error(exc),
        )
