"""HTML, JSON, and CSV optimization report generator for QueryTrellis.

Strictly excludes database passwords, DSNs, and sensitive credentials from
every generated report artifact.
"""
from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from src.advisor.index_recommender import IndexRecommendation
from src.benchmark.comparator import QueryComparisonResult
from src.benchmark.runner import METHODOLOGY_NOTES, BenchmarkSummary
from src.config.settings import ConnectionConfig
from src.explain.plan_analyzer import PlanInsight
from src.explain.plan_parser import ParsedExplainPlan
from src.sql_analysis.antipattern_detector import AntiPatternFinding


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_json_report(
    *,
    title: str,
    sql_text: str,
    formatted_sql: str | None = None,
    connection_info: ConnectionConfig | dict[str, Any] | None = None,
    server_version: str = "",
    plan: ParsedExplainPlan | None = None,
    plan_insights: list[PlanInsight] | None = None,
    antipatterns: list[AntiPatternFinding] | None = None,
    index_recommendations: list[IndexRecommendation] | None = None,
    benchmark: BenchmarkSummary | None = None,
    comparison: QueryComparisonResult | None = None,
    optimization_notes: str = "",
) -> str:
    """Build a sanitized JSON optimization report."""
    if isinstance(connection_info, ConnectionConfig):
        safe_conn = connection_info.to_safe_dict()
    elif isinstance(connection_info, dict):
        safe_conn = {
            k: v
            for k, v in connection_info.items()
            if "password" not in k.lower() and "secret" not in k.lower() and "dsn" not in k.lower()
        }
    else:
        safe_conn = {}

    payload: dict[str, Any] = {
        "report_meta": {
            "tool": "QueryTrellis — PostgreSQL Query Performance & Optimization Workbench",
            "title": title,
            "generated_at": _utc_stamp(),
        },
        "database_info": {
            **safe_conn,
            "server_version": server_version or "Unavailable",
        },
        "query": {
            "sql_text": sql_text,
            "formatted_sql": formatted_sql or sql_text,
        },
        "explain_plan_summary": plan.to_summary_dict() if plan else None,
        "plan_insights": [asdict(i) for i in (plan_insights or [])],
        "antipatterns": [asdict(a) for a in (antipatterns or [])],
        "index_recommendations": [asdict(r) for r in (index_recommendations or [])],
        "benchmark": benchmark.to_dict() if benchmark else None,
        "comparison": comparison.to_dict() if comparison else None,
        "optimization_notes": optimization_notes,
        "methodology_caveats": METHODOLOGY_NOTES,
    }
    return json.dumps(payload, indent=2, default=str)


def build_benchmark_csv(benchmark: BenchmarkSummary) -> str:
    """Export tabular per-run benchmark timings to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "label",
            "run_index",
            "is_warmup",
            "client_wall_ms",
            "pg_planning_ms",
            "pg_execution_ms",
            "rows_returned",
            "shared_hit_blocks",
            "shared_read_blocks",
        ]
    )
    rows_to_write = []
    if benchmark.warmup_iteration is not None:
        rows_to_write.append(benchmark.warmup_iteration)
    rows_to_write.extend(benchmark.iterations)

    for it in rows_to_write:
        writer.writerow(
            [
                benchmark.label,
                it.run_index,
                it.is_warmup,
                it.client_wall_ms,
                it.pg_planning_ms if it.pg_planning_ms is not None else "",
                it.pg_execution_ms if it.pg_execution_ms is not None else "",
                it.rows_returned if it.rows_returned is not None else "",
                it.shared_hit_blocks if it.shared_hit_blocks is not None else "",
                it.shared_read_blocks if it.shared_read_blocks is not None else "",
            ]
        )
    return buf.getvalue()


def build_plan_nodes_csv(plan: ParsedExplainPlan) -> str:
    """Export parsed execution plan nodes to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "node_id",
            "depth",
            "node_type",
            "relation_name",
            "index_name",
            "startup_cost",
            "total_cost",
            "plan_rows",
            "actual_rows",
            "actual_total_time_ms",
            "actual_loops",
            "self_time_ms",
            "shared_hit_blocks",
            "shared_read_blocks",
            "rows_removed_by_filter",
            "sort_method",
            "sort_space_type",
        ]
    )
    for n in plan.all_nodes:
        writer.writerow(
            [
                n.node_id,
                n.depth,
                n.node_type,
                n.relation_name or "",
                n.index_name or "",
                n.startup_cost if n.startup_cost is not None else "",
                n.total_cost if n.total_cost is not None else "",
                n.plan_rows if n.plan_rows is not None else "",
                n.actual_rows if n.actual_rows is not None else "",
                n.actual_total_time if n.actual_total_time is not None else "",
                n.actual_loops if n.actual_loops is not None else "",
                n.self_time_ms if n.self_time_ms is not None else "",
                n.shared_hit_blocks if n.shared_hit_blocks is not None else "",
                n.shared_read_blocks if n.shared_read_blocks is not None else "",
                n.rows_removed_by_filter if n.rows_removed_by_filter is not None else "",
                n.sort_method or "",
                n.sort_space_type or "",
            ]
        )
    return buf.getvalue()


def build_html_report(
    *,
    title: str,
    sql_text: str,
    formatted_sql: str | None = None,
    connection_info: ConnectionConfig | dict[str, Any] | None = None,
    server_version: str = "",
    plan: ParsedExplainPlan | None = None,
    plan_insights: list[PlanInsight] | None = None,
    antipatterns: list[AntiPatternFinding] | None = None,
    index_recommendations: list[IndexRecommendation] | None = None,
    benchmark: BenchmarkSummary | None = None,
    comparison: QueryComparisonResult | None = None,
    optimization_notes: str = "",
) -> str:
    """Generate a self-contained, clean technical HTML report."""
    esc = html.escape
    if isinstance(connection_info, ConnectionConfig):
        safe_conn = connection_info.to_safe_dict()
    elif isinstance(connection_info, dict):
        safe_conn = {
            k: v
            for k, v in connection_info.items()
            if "password" not in k.lower() and "secret" not in k.lower()
        }
    else:
        safe_conn = {}

    db_name = str(safe_conn.get("database", "N/A"))
    host_port = f"{safe_conn.get('host', 'N/A')}:{safe_conn.get('port', 'N/A')}"
    username = str(safe_conn.get("username", "N/A"))

    def _fmt(val: float | int | None, suffix: str = "") -> str:
        if val is None:
            return "Unavailable"
        return f"{val}{suffix}"

    # Metrics summary cards
    exec_ms = plan.execution_time_ms if plan else None
    plan_ms = plan.planning_time_ms if plan else None
    tot_cost = plan.total_cost if plan else None
    act_rows = plan.root_actual_rows if plan else None

    antipattern_rows = ""
    if antipatterns:
        for ap in antipatterns:
            antipattern_rows += (
                f"<tr>"
                f"<td><strong>{esc(ap.severity)}</strong></td>"
                f"<td>{esc(ap.issue_name)}<br><small>{esc(ap.confidence)} confidence ({esc(ap.evidence_basis)})</small></td>"
                f"<td><code>{esc(ap.affected_fragment)}</code></td>"
                f"<td>{esc(ap.explanation)}<br><em>When acceptable:</em> {esc(ap.when_acceptable)}</td>"
                f"<td>{esc(ap.suggested_improvement)}</td>"
                f"</tr>"
            )
    else:
        antipattern_rows = "<tr><td colspan='5'>No SQL anti-patterns flagged for this query.</td></tr>"

    rec_blocks = ""
    if index_recommendations:
        for r in index_recommendations:
            rec_blocks += (
                f"<div class='card'>"
                f"<h4>{esc(r.rec_id)} &mdash; {esc(r.index_type)} on <code>{esc(r.table_name)}</code> ({esc(r.confidence)} confidence)</h4>"
                f"<p><strong>Related Condition:</strong> <code>{esc(r.related_condition)}</code></p>"
                f"<pre>{esc(r.suggested_sql)}</pre>"
                f"<p><strong>Why it helps:</strong> {esc(r.why_it_helps)}</p>"
                f"<p><strong>Existing Index Check:</strong> {esc(r.existing_index_status)}</p>"
                f"<p><strong>Write &amp; Storage Overhead:</strong> {esc(r.write_and_storage_overhead)}</p>"
                f"<p><strong>When It May Not Help:</strong> {esc(r.when_not_helpful)}</p>"
                f"</div>"
            )
    else:
        rec_blocks = "<p>No additional index recommendations generated for this query.</p>"

    insight_rows = ""
    if plan_insights:
        for ins in plan_insights:
            insight_rows += (
                f"<tr>"
                f"<td><strong>{esc(ins.severity)}</strong></td>"
                f"<td>{esc(ins.title)}</td>"
                f"<td><code>{esc(ins.node_label)}</code></td>"
                f"<td>{esc(ins.observation)}<br>{esc(ins.interpretation)}</td>"
                f"<td>{esc(ins.recommendation)}</td>"
                f"</tr>"
            )
    else:
        insight_rows = "<tr><td colspan='5'>No execution plan bottlenecks flagged.</td></tr>"

    comparison_section = ""
    if comparison:
        comparison_section = f"""
        <section>
          <h2>Before &amp; After Query Comparison</h2>
          <p><strong>Verdict:</strong> {esc(comparison.verdict)} &mdash; {esc(comparison.verdict_summary)}</p>
          <table>
            <thead><tr><th>Metric</th><th>{esc(comparison.baseline_label)}</th><th>{esc(comparison.optimized_label)}</th><th>Delta</th></tr></thead>
            <tbody>
              <tr><td>Execution Time (ms)</td><td>{_fmt(comparison.baseline_time_ms)}</td><td>{_fmt(comparison.optimized_time_ms)}</td><td>{_fmt(comparison.time_diff_ms, ' ms')} ({_fmt(comparison.pct_change, '%')})</td></tr>
              <tr><td>Total Plan Cost</td><td>{_fmt(comparison.baseline_cost)}</td><td>{_fmt(comparison.optimized_cost)}</td><td>{_fmt(comparison.cost_diff)} ({_fmt(comparison.cost_pct_change, '%')})</td></tr>
              <tr><td>Rows Returned</td><td>{_fmt(comparison.baseline_rows)}</td><td>{_fmt(comparison.optimized_rows)}</td><td>{'Match' if comparison.row_count_matches else ('Mismatch' if comparison.row_count_matches is False else 'Unavailable')}</td></tr>
              <tr><td>Indexes Added</td><td colspan="3">{esc(', '.join(comparison.indexes_added) or 'None')}</td></tr>
              <tr><td>Resolved Anti-Patterns</td><td colspan="3">{esc(', '.join(comparison.resolved_antipatterns) or 'None')}</td></tr>
            </tbody>
          </table>
        </section>
        """

    bench_section = ""
    if benchmark and benchmark.success:
        bench_section = f"""
        <section>
          <h2>Benchmark Summary ({esc(benchmark.label)})</h2>
          <p>Measured runs: {benchmark.repeat_count} | Warmup run excluded: {'Yes' if benchmark.warmup_used else 'No'}</p>
          <table>
            <thead><tr><th>Metric</th><th>Client Wall Time (ms)</th><th>PostgreSQL Execution Time (ms)</th></tr></thead>
            <tbody>
              <tr><td>Minimum</td><td>{benchmark.min_ms}</td><td>{_fmt(benchmark.pg_exec_min_ms)}</td></tr>
              <tr><td>Median</td><td>{benchmark.median_ms}</td><td>{_fmt(benchmark.pg_exec_median_ms)}</td></tr>
              <tr><td>Mean (Average)</td><td>{benchmark.mean_ms}</td><td>{_fmt(benchmark.pg_exec_mean_ms)}</td></tr>
              <tr><td>Maximum</td><td>{benchmark.max_ms}</td><td>{_fmt(benchmark.pg_exec_max_ms)}</td></tr>
              <tr><td>P95</td><td>{benchmark.p95_ms}</td><td>Unavailable</td></tr>
            </tbody>
          </table>
        </section>
        """

    plan_tree_text = plan.to_text_tree() if plan else "Execution plan not captured."
    notes_block = f"<section><h2>Optimization Notes</h2><p>{esc(optimization_notes)}</p></section>" if optimization_notes.strip() else ""
    caveats_li = "".join(f"<li>{esc(n)}</li>" for n in METHODOLOGY_NOTES)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{esc(title)} — QueryTrellis Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #0F172A; background: #F8FAFC; margin: 0; padding: 24px; line-height: 1.5; }}
    .container {{ max-width: 1100px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 28px 34px; }}
    header {{ border-bottom: 2px solid #0F766E; padding-bottom: 14px; margin-bottom: 22px; }}
    h1 {{ margin: 0 0 6px 0; font-size: 22px; color: #0F172A; }}
    h2 {{ font-size: 16px; color: #0F172A; border-bottom: 1px solid #E2E8F0; padding-bottom: 6px; margin-top: 24px; }}
    h4 {{ margin: 0 0 8px 0; font-size: 14px; color: #0F766E; }}
    .meta {{ color: #475569; font-size: 13px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
    .kpi {{ background: #F8FAFC; border: 1px solid #E2E8F0; padding: 12px; }}
    .kpi-label {{ font-size: 11px; text-transform: uppercase; color: #475569; letter-spacing: 0.04em; }}
    .kpi-val {{ font-size: 18px; font-weight: 600; color: #0F172A; margin-top: 4px; }}
    pre {{ background: #F8FAFC; border: 1px solid #E2E8F0; padding: 12px; overflow-x: auto; font-family: Consolas, "Courier New", monospace; font-size: 12px; }}
    code {{ font-family: Consolas, "Courier New", monospace; background: #F1F5F9; padding: 1px 4px; font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
    th, td {{ border: 1px solid #E2E8F0; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #F1F5F9; color: #0F172A; font-weight: 600; }}
    .card {{ border: 1px solid #CBD5E1; background: #F8FAFC; padding: 14px; margin-bottom: 12px; }}
    .advisory {{ background: #F0FDFA; border-left: 4px solid #0F766E; padding: 10px 14px; font-size: 13px; margin: 12px 0; }}
    footer {{ margin-top: 28px; padding-top: 12px; border-top: 1px solid #E2E8F0; font-size: 12px; color: #64748B; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{esc(title)}</h1>
      <div class="meta">
        Generated: {esc(_utc_stamp())} | Database: <strong>{esc(db_name)}</strong> @ {esc(host_port)} (User: {esc(username)})<br />
        Server: {esc(server_version or 'Unavailable')}
      </div>
    </header>

    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-label">PG Execution Time</div><div class="kpi-val">{_fmt(exec_ms, ' ms')}</div></div>
      <div class="kpi"><div class="kpi-label">PG Planning Time</div><div class="kpi-val">{_fmt(plan_ms, ' ms')}</div></div>
      <div class="kpi"><div class="kpi-label">Estimated Total Cost</div><div class="kpi-val">{_fmt(tot_cost)}</div></div>
      <div class="kpi"><div class="kpi-label">Actual Root Rows</div><div class="kpi-val">{_fmt(act_rows)}</div></div>
    </div>

    <section>
      <h2>Analyzed SQL Statement</h2>
      <pre>{esc(formatted_sql or sql_text)}</pre>
    </section>

    <section>
      <h2>PostgreSQL Execution Plan Tree</h2>
      <pre>{esc(plan_tree_text)}</pre>
    </section>

    <section>
      <h2>Execution Plan Diagnostic Insights</h2>
      <table>
        <thead><tr><th>Severity</th><th>Insight</th><th>Plan Node</th><th>Observation &amp; Interpretation</th><th>Recommendation</th></tr></thead>
        <tbody>{insight_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Detected SQL Anti-Patterns</h2>
      <table>
        <thead><tr><th>Severity</th><th>Issue</th><th>SQL Fragment</th><th>Explanation &amp; Context</th><th>Suggested Rewrite</th></tr></thead>
        <tbody>{antipattern_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Advisory Index Recommendations</h2>
      <div class="advisory">Notice: Index DDL statements below are strictly advisory recommendations. QueryTrellis never applies schema changes automatically.</div>
      {rec_blocks}
    </section>

    {bench_section}
    {comparison_section}
    {notes_block}

    <section>
      <h2>Benchmark &amp; Measurement Caveats</h2>
      <ul>{caveats_li}</ul>
    </section>

    <footer>
      QueryTrellis &mdash; PostgreSQL Query Performance &amp; Optimization Workbench. Credentials are never stored or exported in reports.
    </footer>
  </div>
</body>
</html>
"""
