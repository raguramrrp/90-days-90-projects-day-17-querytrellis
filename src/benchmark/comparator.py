"""Before-and-after SQL query optimization comparison engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.benchmark.runner import BenchmarkSummary
from src.explain.plan_parser import ParsedExplainPlan
from src.sql_analysis.antipattern_detector import AntiPatternFinding


@dataclass(slots=True)
class QuerySnapshot:
    """Captured state (SQL, plan, timing, anti-patterns) for a baseline or candidate query."""

    label: str
    sql_text: str
    plan: ParsedExplainPlan | None = None
    benchmark: BenchmarkSummary | None = None
    antipatterns: list[AntiPatternFinding] = field(default_factory=list)
    observed_duration_ms: float | None = None
    rows_returned: int | None = None

    def effective_time_ms(self) -> float | None:
        """Return best available measured server/benchmark execution duration in ms."""
        if self.benchmark and self.benchmark.success:
            if self.benchmark.pg_exec_median_ms is not None:
                return self.benchmark.pg_exec_median_ms
            return self.benchmark.median_ms
        if self.plan and self.plan.execution_time_ms is not None:
            return self.plan.execution_time_ms
        return self.observed_duration_ms

    def effective_rows(self) -> int | None:
        if self.plan and self.plan.root_actual_rows is not None:
            return self.plan.root_actual_rows
        if self.rows_returned is not None:
            return self.rows_returned
        if self.benchmark and self.benchmark.iterations:
            return self.benchmark.iterations[-1].rows_returned
        return None


@dataclass(slots=True)
class QueryComparisonResult:
    """Evidence-based comparison between Original (A) and Optimized (B) query versions."""

    baseline_label: str
    optimized_label: str
    baseline_sql: str
    optimized_sql: str
    baseline_time_ms: float | None
    optimized_time_ms: float | None
    time_diff_ms: float | None
    pct_change: float | None  # Negative means faster (reduction); positive means slower (regression)
    speedup_factor: float | None
    baseline_cost: float | None
    optimized_cost: float | None
    cost_diff: float | None
    cost_pct_change: float | None
    baseline_rows: int | None
    optimized_rows: int | None
    row_count_matches: bool | None
    baseline_nodes: list[str]
    optimized_nodes: list[str]
    nodes_added: list[str]
    nodes_removed: list[str]
    baseline_indexes: list[str]
    optimized_indexes: list[str]
    indexes_added: list[str]
    indexes_removed: list[str]
    resolved_antipatterns: list[str]
    remaining_antipatterns: list[str]
    introduced_antipatterns: list[str]
    verdict: str  # "Improved" | "Regressed" | "No Significant Change" | "Inconclusive" | "Row Count Mismatch"
    verdict_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_label": self.baseline_label,
            "optimized_label": self.optimized_label,
            "baseline_sql": self.baseline_sql,
            "optimized_sql": self.optimized_sql,
            "baseline_time_ms": self.baseline_time_ms,
            "optimized_time_ms": self.optimized_time_ms,
            "time_diff_ms": self.time_diff_ms,
            "pct_change": self.pct_change,
            "speedup_factor": self.speedup_factor,
            "baseline_cost": self.baseline_cost,
            "optimized_cost": self.optimized_cost,
            "cost_diff": self.cost_diff,
            "cost_pct_change": self.cost_pct_change,
            "baseline_rows": self.baseline_rows,
            "optimized_rows": self.optimized_rows,
            "row_count_matches": self.row_count_matches,
            "nodes_added": self.nodes_added,
            "nodes_removed": self.nodes_removed,
            "indexes_added": self.indexes_added,
            "indexes_removed": self.indexes_removed,
            "resolved_antipatterns": self.resolved_antipatterns,
            "remaining_antipatterns": self.remaining_antipatterns,
            "introduced_antipatterns": self.introduced_antipatterns,
            "verdict": self.verdict,
            "verdict_summary": self.verdict_summary,
        }


def compare_queries(baseline: QuerySnapshot, optimized: QuerySnapshot) -> QueryComparisonResult:
    """Compute an honest, evidence-driven comparison between two query snapshots."""
    t_a = baseline.effective_time_ms()
    t_b = optimized.effective_time_ms()

    time_diff_ms: float | None = None
    pct_change: float | None = None
    speedup: float | None = None
    if t_a is not None and t_b is not None:
        time_diff_ms = round(t_b - t_a, 3)
        if t_a > 0:
            pct_change = round(((t_b - t_a) / t_a) * 100.0, 2)
        if t_b > 0:
            speedup = round(t_a / t_b, 2)

    cost_a = baseline.plan.total_cost if baseline.plan else None
    cost_b = optimized.plan.total_cost if optimized.plan else None
    cost_diff: float | None = None
    cost_pct: float | None = None
    if cost_a is not None and cost_b is not None:
        cost_diff = round(cost_b - cost_a, 2)
        if cost_a > 0:
            cost_pct = round(((cost_b - cost_a) / cost_a) * 100.0, 2)

    rows_a = baseline.effective_rows()
    rows_b = optimized.effective_rows()
    row_match: bool | None = (rows_a == rows_b) if (rows_a is not None and rows_b is not None) else None

    nodes_a = baseline.plan.node_types if baseline.plan else []
    nodes_b = optimized.plan.node_types if optimized.plan else []
    set_na, set_nb = set(nodes_a), set(nodes_b)

    idx_a = baseline.plan.used_indexes if baseline.plan else []
    idx_b = optimized.plan.used_indexes if optimized.plan else []
    set_ia, set_ib = set(idx_a), set(idx_b)

    ap_a = {f.issue_name for f in baseline.antipatterns}
    ap_b = {f.issue_name for f in optimized.antipatterns}
    resolved_ap = sorted(ap_a - ap_b)
    remaining_ap = sorted(ap_a & ap_b)
    introduced_ap = sorted(ap_b - ap_a)

    # Strictly evidence-based verdict (never claim success without measurement!)
    if row_match is False:
        verdict = "Row Count Mismatch"
        verdict_summary = (
            f"Candidate returned {rows_b:,} row(s) vs baseline {rows_a:,} row(s). "
            "Verify semantic equivalence before treating timing differences as a valid optimization."
        )
    elif t_a is None or t_b is None:
        verdict = "Inconclusive"
        verdict_summary = (
            "Measured execution timing is missing for at least one query version. "
            "Run EXPLAIN ANALYZE or Benchmark Lab on both versions to evaluate performance."
        )
    elif pct_change is not None and pct_change <= -5.0 and abs(time_diff_ms or 0.0) >= 0.05:
        verdict = "Improved"
        verdict_summary = (
            f"Measured execution time improved by {abs(pct_change):.1f}% "
            f"({t_a:.3f} ms -> {t_b:.3f} ms, {speedup:.2f}x faster)."
        )
    elif pct_change is not None and pct_change >= 5.0 and abs(time_diff_ms or 0.0) >= 0.05:
        verdict = "Regressed"
        verdict_summary = (
            f"Measured execution time regressed (slower by {pct_change:.1f}%: "
            f"{t_a:.3f} ms -> {t_b:.3f} ms)."
        )
    else:
        verdict = "No Significant Change"
        verdict_summary = (
            f"Measured timing difference ({t_a:.3f} ms vs {t_b:.3f} ms) is within typical "
            "cache/run-to-run variance (<5% or <0.05 ms)."
        )

    return QueryComparisonResult(
        baseline_label=baseline.label,
        optimized_label=optimized.label,
        baseline_sql=baseline.sql_text,
        optimized_sql=optimized.sql_text,
        baseline_time_ms=t_a,
        optimized_time_ms=t_b,
        time_diff_ms=time_diff_ms,
        pct_change=pct_change,
        speedup_factor=speedup,
        baseline_cost=cost_a,
        optimized_cost=cost_b,
        cost_diff=cost_diff,
        cost_pct_change=cost_pct,
        baseline_rows=rows_a,
        optimized_rows=rows_b,
        row_count_matches=row_match,
        baseline_nodes=nodes_a,
        optimized_nodes=nodes_b,
        nodes_added=sorted(set_nb - set_na),
        nodes_removed=sorted(set_na - set_nb),
        baseline_indexes=idx_a,
        optimized_indexes=idx_b,
        indexes_added=sorted(set_ib - set_ia),
        indexes_removed=sorted(set_ia - set_ib),
        resolved_antipatterns=resolved_ap,
        remaining_antipatterns=remaining_ap,
        introduced_antipatterns=introduced_ap,
        verdict=verdict,
        verdict_summary=verdict_summary,
    )
