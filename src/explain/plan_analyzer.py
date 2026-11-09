"""Execution plan bottleneck and nuance analyzer for PostgreSQL plans."""
from __future__ import annotations

from dataclasses import dataclass

from src.db.connection_manager import DatabaseCatalog
from src.explain.plan_parser import ParsedExplainPlan, PlanNode


@dataclass(slots=True)
class PlanInsight:
    """Actionable diagnostic insight derived from an EXPLAIN / EXPLAIN ANALYZE plan."""

    insight_id: str
    title: str
    severity: str  # "Info" | "Low" | "Medium" | "High"
    node_label: str
    node_id: int
    observation: str
    interpretation: str
    recommendation: str


def analyze_explain_plan(
    plan: ParsedExplainPlan,
    catalog: DatabaseCatalog | None = None,
    large_table_threshold: int = 5000,
) -> list[PlanInsight]:
    """Inspect parsed EXPLAIN tree nodes for bottlenecks while respecting planner trade-offs."""
    insights: list[PlanInsight] = []

    for node in plan.all_nodes:
        # --------------------------------------------------------------
        # 1. Sequential Scan nuance (large vs small / high selectivity vs bulk)
        # --------------------------------------------------------------
        if node.node_type == "Seq Scan":
            tbl = catalog.find_table(node.relation_name or "") if (catalog and node.relation_name) else None
            est_table_rows = tbl.estimated_rows if tbl else None
            removed = node.rows_removed_by_filter or 0
            actual = node.actual_rows if node.actual_rows is not None else (node.plan_rows or 0)
            total_scanned = actual + removed

            is_large = (est_table_rows is not None and est_table_rows >= large_table_threshold) or (
                total_scanned >= large_table_threshold
            )
            discard_ratio = (removed / total_scanned) if total_scanned > 0 else 0.0

            if is_large and node.filter_cond and discard_ratio >= 0.70:
                sev = "High" if discard_ratio >= 0.90 or (node.self_time_ms or 0) >= 20.0 else "Medium"
                insights.append(
                    PlanInsight(
                        insight_id="EP001",
                        title="Selective Sequential Scan on Large Table",
                        severity=sev,
                        node_label=node.label,
                        node_id=node.node_id,
                        observation=(
                            f"Seq Scan on '{node.relation_name}' evaluated Filter ({node.filter_cond}) and "
                            f"discarded {removed:,} of {total_scanned:,} rows ({discard_ratio:.1%} filtered out)."
                        ),
                        interpretation=(
                            "PostgreSQL read the full heap table because no suitable index matched the filter "
                            "or the predicate was non-sargable."
                        ),
                        recommendation=(
                            "Review the Filter expression and check Index Recommendations for a targeted B-tree or partial index."
                        ),
                    )
                )
            elif est_table_rows is not None and est_table_rows < 1000:
                insights.append(
                    PlanInsight(
                        insight_id="EP001_INFO",
                        title="Optimal Sequential Scan on Small Table",
                        severity="Info",
                        node_label=node.label,
                        node_id=node.node_id,
                        observation=f"Seq Scan read small table '{node.relation_name}' (~{est_table_rows:,} rows).",
                        interpretation=(
                            "A sequential scan on a small table fitting in a few 8KB pages is faster than "
                            "traversing a B-tree index plus heap random I/O."
                        ),
                        recommendation="No index change needed for table size alone.",
                    )
                )
            elif is_large and not node.filter_cond:
                insights.append(
                    PlanInsight(
                        insight_id="EP001_BULK",
                        title="Unfiltered Full-Table Sequential Scan",
                        severity="Low",
                        node_label=node.label,
                        node_id=node.node_id,
                        observation=f"Seq Scan read '{node.relation_name}' without a pushdown Filter.",
                        interpretation=(
                            "When reading most or all rows of a table (e.g., global aggregation or wide join), "
                            "PostgreSQL intentionally chooses Seq Scan over Index Scan."
                        ),
                        recommendation="Confirm whether a WHERE filter or LIMIT can narrow the working set.",
                    )
                )

        # --------------------------------------------------------------
        # 2. Estimate vs Actual Row Cardinality Misestimation
        # --------------------------------------------------------------
        factor = node.estimation_factor
        if factor is not None and node.actual_rows is not None and node.plan_rows is not None:
            diff_abs = abs(node.actual_rows - node.plan_rows)
            if factor >= 5.0 and diff_abs >= 100:
                sev = "High" if factor >= 25.0 and diff_abs >= 1000 else "Medium"
                insights.append(
                    PlanInsight(
                        insight_id="EP002",
                        title=f"Row Cardinality Misestimation ({factor}x difference)",
                        severity=sev,
                        node_label=node.label,
                        node_id=node.node_id,
                        observation=(
                            f"Planner estimated {node.plan_rows:,} row(s), but execution produced {node.actual_rows:,} row(s)."
                        ),
                        interpretation=(
                            "Large row misestimates can mislead PostgreSQL into picking Nested Loop instead of Hash Join "
                            "(or under-allocating hash/sort memory)."
                        ),
                        recommendation=(
                            f"Run `ANALYZE {node.relation_name or ''}` if statistics are stale, or consider "
                            "`CREATE STATISTICS` for correlated multi-column filters."
                        ),
                    )
                )

        # --------------------------------------------------------------
        # 3. Disk-Based Sort or Large Sort Operation
        # --------------------------------------------------------------
        if node.node_type == "Sort":
            if node.sort_space_type == "Disk":
                insights.append(
                    PlanInsight(
                        insight_id="EP003",
                        title="Disk-Spilled Sort Operation",
                        severity="High",
                        node_label=node.label,
                        node_id=node.node_id,
                        observation=(
                            f"Sort ({node.sort_method or 'external'}) spilled {node.sort_space_used or 0:,} kB to temporary disk."
                        ),
                        interpretation=(
                            "Sorting exceeded the session `work_mem` budget and wrote temporary run files to disk, "
                            "substantially increasing I/O latency."
                        ),
                        recommendation=(
                            "Filter earlier, add a LIMIT, align an index with the ORDER BY key to eliminate sorting, "
                            "or review `work_mem` sizing."
                        ),
                    )
                )
            elif (node.self_time_ms or 0) >= 15.0 or (node.actual_rows or 0) >= 10000:
                insights.append(
                    PlanInsight(
                        insight_id="EP003_MEM",
                        title="Expensive In-Memory Sort",
                        severity="Medium",
                        node_label=node.label,
                        node_id=node.node_id,
                        observation=(
                            f"Sort ({node.sort_method or 'in-memory'}) processed {node.actual_rows or node.plan_rows or 0:,} rows"
                            + (f" using {node.sort_space_used:,} kB." if node.sort_space_used else ".")
                        ),
                        interpretation="Sorting large intermediate sets adds CPU and memory overhead.",
                        recommendation="Consider a composite index matching filter + ORDER BY columns when sorting top-N queries.",
                    )
                )

        # --------------------------------------------------------------
        # 4. High Loop Count (Nested Loop / SubPlan)
        # --------------------------------------------------------------
        if node.actual_loops is not None and node.actual_loops >= 100:
            sev = "High" if (node.actual_loops >= 1000 or (node.inclusive_time_ms or 0) >= 25.0) else "Medium"
            insights.append(
                PlanInsight(
                    insight_id="EP004",
                    title=f"High Execution Loop Count ({node.actual_loops:,} loops)",
                    severity=sev,
                    node_label=node.label,
                    node_id=node.node_id,
                    observation=(
                        f"Node executed {node.actual_loops:,} times"
                        + (f" ({node.inclusive_time_ms:.2f} ms cumulative)." if node.inclusive_time_ms is not None else ".")
                    ),
                    interpretation=(
                        "Repeated inner execution typically occurs beneath a Nested Loop join or correlated SubPlan. "
                        "Even fast sub-millisecond scans add up over thousands of loops."
                    ),
                    recommendation=(
                        "Ensure an index exists on the inner join/filter key, or rewrite correlated subqueries into CTE/Hash Joins."
                    ),
                )
            )

        # --------------------------------------------------------------
        # 5. Significant Buffer Disk Reads or Temp Blocks
        # --------------------------------------------------------------
        hits = node.shared_hit_blocks or 0
        reads = node.shared_read_blocks or 0
        if reads >= 500 and (hits == 0 or reads > hits):
            insights.append(
                PlanInsight(
                    insight_id="EP005",
                    title=f"High Shared Buffer Disk/OS Reads ({reads:,} blocks)",
                    severity="Medium" if reads < 5000 else "High",
                    node_label=node.label,
                    node_id=node.node_id,
                    observation=f"Node incurred {reads:,} shared block reads vs {hits:,} shared buffer hits (~{reads * 8 / 1024:.1f} MB read).",
                    interpretation=(
                        "Cold cache or unindexed wide scans forced PostgreSQL to pull pages from OS cache/disk rather than shared buffers."
                    ),
                    recommendation="Reduce scanned pages via selective indexes or narrower projections; note cold vs warm cache effects during benchmarking.",
                )
            )

        if node.temp_written_blocks and node.temp_written_blocks > 0 and node.node_type != "Sort":
            insights.append(
                PlanInsight(
                    insight_id="EP006",
                    title=f"Temporary Disk Spill ({node.temp_written_blocks:,} blocks)",
                    severity="High",
                    node_label=node.label,
                    node_id=node.node_id,
                    observation=f"{node.node_type} wrote {node.temp_written_blocks:,} temp blocks (~{node.temp_written_blocks * 8 / 1024:.1f} MB).",
                    interpretation="Hash table or materialization spilled out of `work_mem` onto disk.",
                    recommendation="Filter rows before joining/aggregating, or check `work_mem`.",
                )
            )

        # --------------------------------------------------------------
        # 6. Parallel Worker Under-Allocation
        # --------------------------------------------------------------
        if (
            node.workers_planned is not None
            and node.workers_launched is not None
            and node.workers_launched < node.workers_planned
        ):
            insights.append(
                PlanInsight(
                    insight_id="EP007",
                    title="Fewer Parallel Workers Launched Than Planned",
                    severity="Low",
                    node_label=node.label,
                    node_id=node.node_id,
                    observation=f"Planned {node.workers_planned} parallel workers, launched {node.workers_launched}.",
                    interpretation="Server `max_parallel_workers` or `max_worker_processes` constrained parallel execution.",
                    recommendation="Expected under concurrent load; compare benchmark timings carefully.",
                )
            )

    return insights
