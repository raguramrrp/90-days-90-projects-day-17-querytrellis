"""Multi-run PostgreSQL query performance benchmark runner."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

import psycopg

from src.db.safe_executor import run_explain_plan
from src.explain.plan_parser import ParsedExplainPlan, parse_explain_json
from src.sql_analysis.parser_validator import ValidationResult, validate_read_only_sql

METHODOLOGY_NOTES = [
    "Cold vs. Warm Cache: Run 1 may read pages from disk/OS cache (Shared Read Blocks), while subsequent runs hit PostgreSQL Shared Buffers.",
    "Database Load & Concurrency: Concurrent queries, autovacuum, or background checkpoints on the host can introduce run-to-run variance.",
    "Client vs. Server Time: Client-observed round-trip duration includes Python driver and IPC/TCP overhead; PostgreSQL Execution Time isolates server plan execution.",
    "Planner Behavior: Parameter changes, stale statistics, or memory settings (work_mem) can alter plan selection across workloads.",
    "Interpretation: Local benchmark results do not represent guaranteed production throughput under concurrency.",
]


@dataclass(slots=True)
class BenchmarkIteration:
    """Timing and buffer telemetry for a single measured iteration."""

    run_index: int
    is_warmup: bool
    client_wall_ms: float
    pg_planning_ms: float | None
    pg_execution_ms: float | None
    rows_returned: int | None
    shared_hit_blocks: int | None
    shared_read_blocks: int | None


@dataclass(slots=True)
class BenchmarkSummary:
    """Aggregate benchmark summary across measured iterations."""

    success: bool
    label: str
    sql_text: str
    sql_hash: str
    repeat_count: int
    warmup_used: bool
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    stdev_ms: float = 0.0
    pg_exec_min_ms: float | None = None
    pg_exec_max_ms: float | None = None
    pg_exec_mean_ms: float | None = None
    pg_exec_median_ms: float | None = None
    iterations: list[BenchmarkIteration] = field(default_factory=list)
    warmup_iteration: BenchmarkIteration | None = None
    representative_plan: ParsedExplainPlan | None = None
    error_message: str = ""
    interrupted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize benchmark summary for reports and comparison."""
        return {
            "label": self.label,
            "sql_hash": self.sql_hash,
            "repeat_count": self.repeat_count,
            "warmup_used": self.warmup_used,
            "client_stats_ms": {
                "min": self.min_ms,
                "max": self.max_ms,
                "mean": self.mean_ms,
                "median": self.median_ms,
                "p95": self.p95_ms,
                "stdev": self.stdev_ms,
            },
            "pg_execution_stats_ms": {
                "min": self.pg_exec_min_ms,
                "max": self.pg_exec_max_ms,
                "mean": self.pg_exec_mean_ms,
                "median": self.pg_exec_median_ms,
            },
            "iterations": [
                {
                    "run_index": it.run_index,
                    "client_wall_ms": it.client_wall_ms,
                    "pg_planning_ms": it.pg_planning_ms,
                    "pg_execution_ms": it.pg_execution_ms,
                    "rows_returned": it.rows_returned,
                    "shared_hit_blocks": it.shared_hit_blocks,
                    "shared_read_blocks": it.shared_read_blocks,
                }
                for it in self.iterations
            ],
        }


def compute_timing_stats(values: list[float]) -> dict[str, float]:
    """Compute min, max, mean, median, p95, and sample stdev cleanly."""
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "p95": 0.0, "stdev": 0.0}
    ordered = sorted(values)
    idx_95 = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return {
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "mean": round(statistics.mean(ordered), 3),
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[idx_95], 3),
        "stdev": round(statistics.stdev(ordered), 3) if len(ordered) >= 2 else 0.0,
    }


def summarize_iterations(
    *,
    label: str,
    validation: ValidationResult,
    iterations: list[BenchmarkIteration],
    warmup_iteration: BenchmarkIteration | None = None,
    representative_plan: ParsedExplainPlan | None = None,
    interrupted: bool = False,
    error_message: str = "",
) -> BenchmarkSummary:
    """Aggregate raw iteration timings into a BenchmarkSummary."""
    if not iterations:
        return BenchmarkSummary(
            success=False,
            label=label,
            sql_text=validation.clean_sql,
            sql_hash=validation.parsed_info.normalized_hash if validation.parsed_info else "",
            repeat_count=0,
            warmup_used=warmup_iteration is not None,
            warmup_iteration=warmup_iteration,
            interrupted=interrupted,
            error_message=error_message or "No benchmark runs completed.",
        )

    client_vals = [it.client_wall_ms for it in iterations]
    cstats = compute_timing_stats(client_vals)

    pg_vals = [it.pg_execution_ms for it in iterations if it.pg_execution_ms is not None]
    pg_stats = compute_timing_stats(pg_vals) if pg_vals else None

    return BenchmarkSummary(
        success=True,
        label=label,
        sql_text=validation.clean_sql,
        sql_hash=validation.parsed_info.normalized_hash if validation.parsed_info else "",
        repeat_count=len(iterations),
        warmup_used=warmup_iteration is not None,
        min_ms=cstats["min"],
        max_ms=cstats["max"],
        mean_ms=cstats["mean"],
        median_ms=cstats["median"],
        p95_ms=cstats["p95"],
        stdev_ms=cstats["stdev"],
        pg_exec_min_ms=pg_stats["min"] if pg_stats else None,
        pg_exec_max_ms=pg_stats["max"] if pg_stats else None,
        pg_exec_mean_ms=pg_stats["mean"] if pg_stats else None,
        pg_exec_median_ms=pg_stats["median"] if pg_stats else None,
        iterations=iterations,
        warmup_iteration=warmup_iteration,
        representative_plan=representative_plan,
        interrupted=interrupted,
        error_message=error_message,
    )


def run_query_benchmark(
    conn: psycopg.Connection[Any],
    sql: str,
    *,
    label: str = "Query Benchmark",
    repeat_count: int = 5,
    include_warmup: bool = False,
    timeout_ms: int = 5000,
    on_progress: Callable[[int, int], None] | None = None,
) -> BenchmarkSummary:
    """Execute a validated read-only SQL query N times and record server + client timings."""
    validation = validate_read_only_sql(sql)
    if not validation.is_valid or not validation.is_read_only:
        return BenchmarkSummary(
            success=False,
            label=label,
            sql_text=sql,
            sql_hash="",
            repeat_count=0,
            warmup_used=include_warmup,
            error_message=validation.error_message or "SQL failed read-only safety validation.",
        )

    repeats = max(1, min(50, int(repeat_count)))
    warmup_it: BenchmarkIteration | None = None
    measured: list[BenchmarkIteration] = []
    rep_plan: ParsedExplainPlan | None = None

    total_steps = repeats + (1 if include_warmup else 0)
    step = 0

    try:
        if include_warmup:
            step += 1
            if on_progress:
                on_progress(step, total_steps)
            res = run_explain_plan(
                conn,
                validation.clean_sql,
                analyze=True,
                buffers=True,
                timeout_ms=timeout_ms,
            )
            if not res.success:
                return BenchmarkSummary(
                    success=False,
                    label=label,
                    sql_text=validation.clean_sql,
                    sql_hash=validation.parsed_info.normalized_hash if validation.parsed_info else "",
                    repeat_count=0,
                    warmup_used=True,
                    error_message=res.error_message,
                )
            plan = parse_explain_json(res.raw_plan_json)
            rep_plan = plan
            warmup_it = BenchmarkIteration(
                run_index=0,
                is_warmup=True,
                client_wall_ms=res.client_duration_ms,
                pg_planning_ms=plan.planning_time_ms,
                pg_execution_ms=plan.execution_time_ms,
                rows_returned=plan.root_actual_rows,
                shared_hit_blocks=plan.total_shared_hit_blocks,
                shared_read_blocks=plan.total_shared_read_blocks,
            )

        for idx in range(1, repeats + 1):
            step += 1
            if on_progress:
                on_progress(step, total_steps)
            res = run_explain_plan(
                conn,
                validation.clean_sql,
                analyze=True,
                buffers=True,
                timeout_ms=timeout_ms,
            )
            if not res.success:
                if measured:
                    return summarize_iterations(
                        label=label,
                        validation=validation,
                        iterations=measured,
                        warmup_iteration=warmup_it,
                        representative_plan=rep_plan,
                        interrupted=True,
                        error_message=f"Benchmark interrupted on run {idx}: {res.error_message}",
                    )
                return BenchmarkSummary(
                    success=False,
                    label=label,
                    sql_text=validation.clean_sql,
                    sql_hash=validation.parsed_info.normalized_hash if validation.parsed_info else "",
                    repeat_count=0,
                    warmup_used=include_warmup,
                    error_message=res.error_message,
                )

            plan = parse_explain_json(res.raw_plan_json)
            rep_plan = plan
            measured.append(
                BenchmarkIteration(
                    run_index=idx,
                    is_warmup=False,
                    client_wall_ms=res.client_duration_ms,
                    pg_planning_ms=plan.planning_time_ms,
                    pg_execution_ms=plan.execution_time_ms,
                    rows_returned=plan.root_actual_rows,
                    shared_hit_blocks=plan.total_shared_hit_blocks,
                    shared_read_blocks=plan.total_shared_read_blocks,
                )
            )
    except KeyboardInterrupt:
        return summarize_iterations(
            label=label,
            validation=validation,
            iterations=measured,
            warmup_iteration=warmup_it,
            representative_plan=rep_plan,
            interrupted=True,
            error_message="Benchmark interrupted by user.",
        )

    return summarize_iterations(
        label=label,
        validation=validation,
        iterations=measured,
        warmup_iteration=warmup_it,
        representative_plan=rep_plan,
    )
