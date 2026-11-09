"""Parser for PostgreSQL EXPLAIN (FORMAT JSON) output into structured PlanNode trees.

Handles both estimate-only EXPLAIN and EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON).
Missing fields (such as Actual Time/Rows when ANALYZE was not run) are preserved
as ``None`` rather than invented.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlanNode:
    """Single node inside a PostgreSQL execution plan tree."""

    node_id: int
    depth: int
    node_type: str
    parent_relationship: str | None = None
    relation_name: str | None = None
    schema_name: str | None = None
    alias: str | None = None
    index_name: str | None = None
    join_type: str | None = None
    strategy: str | None = None
    startup_cost: float | None = None
    total_cost: float | None = None
    plan_rows: int | None = None
    plan_width: int | None = None
    actual_startup_time: float | None = None
    actual_total_time: float | None = None
    actual_rows: int | None = None
    actual_loops: int | None = None
    inclusive_time_ms: float | None = None
    self_time_ms: float | None = None
    shared_hit_blocks: int | None = None
    shared_read_blocks: int | None = None
    shared_dirtied_blocks: int | None = None
    shared_written_blocks: int | None = None
    temp_read_blocks: int | None = None
    temp_written_blocks: int | None = None
    sort_method: str | None = None
    sort_space_used: int | None = None
    sort_space_type: str | None = None
    sort_key: list[str] = field(default_factory=list)
    group_key: list[str] = field(default_factory=list)
    filter_cond: str | None = None
    index_cond: str | None = None
    hash_cond: str | None = None
    merge_cond: str | None = None
    recheck_cond: str | None = None
    rows_removed_by_filter: int | None = None
    rows_removed_by_recheck: int | None = None
    heap_fetches: int | None = None
    workers_planned: int | None = None
    workers_launched: int | None = None
    parallel_aware: bool = False
    subplan_name: str | None = None
    output_columns: list[str] = field(default_factory=list)
    children: list["PlanNode"] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Human-readable compact node label."""
        parts = [self.node_type]
        if self.join_type and self.join_type not in self.node_type:
            parts[0] = f"{self.join_type} {self.node_type}"
        target = self.relation_name or self.alias
        if target and self.index_name:
            parts.append(f"on {target} using {self.index_name}")
        elif target:
            parts.append(f"on {target}")
        elif self.index_name:
            parts.append(f"using {self.index_name}")
        return " ".join(parts)

    @property
    def estimation_factor(self) -> float | None:
        """Return max(actual,1) / max(estimated,1) ratio, or None if not analyzed."""
        if self.actual_rows is None or self.plan_rows is None:
            return None
        est = max(int(self.plan_rows), 1)
        act = max(int(self.actual_rows), 1)
        return round(max(act / est, est / act), 2)

    def to_summary_dict(self) -> dict[str, Any]:
        """Serialize node metrics cleanly for tables, charts, and reports."""
        return {
            "node_id": self.node_id,
            "depth": self.depth,
            "node_type": self.node_type,
            "label": self.label,
            "relation_name": self.relation_name,
            "index_name": self.index_name,
            "startup_cost": self.startup_cost,
            "total_cost": self.total_cost,
            "plan_rows": self.plan_rows,
            "actual_rows": self.actual_rows,
            "actual_startup_time_ms": self.actual_startup_time,
            "actual_total_time_ms": self.actual_total_time,
            "actual_loops": self.actual_loops,
            "inclusive_time_ms": self.inclusive_time_ms,
            "self_time_ms": self.self_time_ms,
            "shared_hit_blocks": self.shared_hit_blocks,
            "shared_read_blocks": self.shared_read_blocks,
            "temp_written_blocks": self.temp_written_blocks,
            "sort_method": self.sort_method,
            "sort_space_used_kb": self.sort_space_used,
            "sort_space_type": self.sort_space_type,
            "rows_removed_by_filter": self.rows_removed_by_filter,
            "estimation_factor": self.estimation_factor,
            "filter_cond": self.filter_cond,
            "index_cond": self.index_cond,
        }


@dataclass(slots=True)
class ParsedExplainPlan:
    """Complete parsed PostgreSQL execution plan."""

    root: PlanNode
    analyzed: bool
    planning_time_ms: float | None = None
    execution_time_ms: float | None = None
    total_cost: float | None = None
    root_plan_rows: int | None = None
    root_actual_rows: int | None = None
    total_shared_hit_blocks: int | None = None
    total_shared_read_blocks: int | None = None
    total_temp_written_blocks: int | None = None
    used_indexes: list[str] = field(default_factory=list)
    node_types: list[str] = field(default_factory=list)
    all_nodes: list[PlanNode] = field(default_factory=list)
    raw_json: Any = None

    def to_text_tree(self) -> str:
        """Render a clean, indented execution plan tree similar to PostgreSQL EXPLAIN."""
        lines: list[str] = []
        for node in self.all_nodes:
            indent = "  " * node.depth
            prefix = "->  " if node.depth > 0 else ""
            rel_tag = f"[{node.parent_relationship}] " if node.parent_relationship and node.depth > 0 else ""
            cost_str = (
                f"cost={node.startup_cost:.2f}..{node.total_cost:.2f} rows={node.plan_rows}"
                if node.startup_cost is not None and node.total_cost is not None
                else "cost=unavailable"
            )
            if node.actual_total_time is not None:
                act_str = (
                    f" | actual time={node.actual_startup_time:.3f}..{node.actual_total_time:.3f} ms "
                    f"rows={node.actual_rows} loops={node.actual_loops}"
                )
            else:
                act_str = " | actual=unavailable (estimate only)"

            lines.append(f"{indent}{prefix}{rel_tag}{node.label}  ({cost_str}{act_str})")
            if node.index_cond:
                lines.append(f"{indent}      Index Cond: {node.index_cond}")
            if node.hash_cond:
                lines.append(f"{indent}      Hash Cond: {node.hash_cond}")
            if node.merge_cond:
                lines.append(f"{indent}      Merge Cond: {node.merge_cond}")
            if node.filter_cond:
                rm = (
                    f" (Rows Removed by Filter: {node.rows_removed_by_filter:,})"
                    if node.rows_removed_by_filter is not None
                    else ""
                )
                lines.append(f"{indent}      Filter: {node.filter_cond}{rm}")
            if node.sort_method:
                lines.append(
                    f"{indent}      Sort Method: {node.sort_method} "
                    f"({node.sort_space_type or 'N/A'}: {node.sort_space_used or 0} kB)"
                )
            if node.shared_hit_blocks is not None or node.shared_read_blocks is not None:
                lines.append(
                    f"{indent}      Buffers: shared hit={node.shared_hit_blocks or 0} "
                    f"read={node.shared_read_blocks or 0}"
                    + (
                        f" temp written={node.temp_written_blocks}"
                        if node.temp_written_blocks
                        else ""
                    )
                )

        if self.planning_time_ms is not None:
            lines.append(f"Planning Time: {self.planning_time_ms:.3f} ms")
        if self.execution_time_ms is not None:
            lines.append(f"Execution Time: {self.execution_time_ms:.3f} ms")
        return "\n".join(lines)

    def to_summary_dict(self) -> dict[str, Any]:
        """Serialize plan summary safely for metadata persistence and reporting."""
        return {
            "analyzed": self.analyzed,
            "planning_time_ms": self.planning_time_ms,
            "execution_time_ms": self.execution_time_ms,
            "total_cost": self.total_cost,
            "root_plan_rows": self.root_plan_rows,
            "root_actual_rows": self.root_actual_rows,
            "total_shared_hit_blocks": self.total_shared_hit_blocks,
            "total_shared_read_blocks": self.total_shared_read_blocks,
            "total_temp_written_blocks": self.total_temp_written_blocks,
            "used_indexes": self.used_indexes,
            "node_types": self.node_types,
            "node_count": len(self.all_nodes),
            "nodes": [n.to_summary_dict() for n in self.all_nodes],
        }


def _opt_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _opt_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _opt_list(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    return [str(val)]


def parse_explain_json(raw_json: Any) -> ParsedExplainPlan:
    """Parse PostgreSQL EXPLAIN (FORMAT JSON) payload into a ParsedExplainPlan tree."""
    if isinstance(raw_json, str):
        try:
            raw_json = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed EXPLAIN JSON string: {exc}") from exc

    if isinstance(raw_json, list):
        if not raw_json or not isinstance(raw_json[0], dict):
            raise ValueError("EXPLAIN JSON array is empty or malformed.")
        envelope = raw_json[0]
    elif isinstance(raw_json, dict):
        envelope = raw_json
    else:
        raise ValueError("Unsupported EXPLAIN JSON payload structure.")

    plan_root_dict = envelope.get("Plan")
    if not isinstance(plan_root_dict, dict):
        raise ValueError("EXPLAIN JSON payload does not contain a 'Plan' object.")

    all_nodes: list[PlanNode] = []
    counter = [0]

    def _walk(node_dict: dict[str, Any], depth: int) -> PlanNode:
        node_id = counter[0]
        counter[0] += 1

        act_total = _opt_float(node_dict.get("Actual Total Time"))
        act_loops = _opt_int(node_dict.get("Actual Loops"))
        inclusive_ms: float | None = None
        if act_total is not None and act_loops is not None:
            inclusive_ms = round(act_total * act_loops, 3)

        node = PlanNode(
            node_id=node_id,
            depth=depth,
            node_type=str(node_dict.get("Node Type", "Unknown")),
            parent_relationship=node_dict.get("Parent Relationship"),
            relation_name=node_dict.get("Relation Name"),
            schema_name=node_dict.get("Schema"),
            alias=node_dict.get("Alias"),
            index_name=node_dict.get("Index Name"),
            join_type=node_dict.get("Join Type"),
            strategy=node_dict.get("Strategy"),
            startup_cost=_opt_float(node_dict.get("Startup Cost")),
            total_cost=_opt_float(node_dict.get("Total Cost")),
            plan_rows=_opt_int(node_dict.get("Plan Rows")),
            plan_width=_opt_int(node_dict.get("Plan Width")),
            actual_startup_time=_opt_float(node_dict.get("Actual Startup Time")),
            actual_total_time=act_total,
            actual_rows=_opt_int(node_dict.get("Actual Rows")),
            actual_loops=act_loops,
            inclusive_time_ms=inclusive_ms,
            shared_hit_blocks=_opt_int(node_dict.get("Shared Hit Blocks")),
            shared_read_blocks=_opt_int(node_dict.get("Shared Read Blocks")),
            shared_dirtied_blocks=_opt_int(node_dict.get("Shared Dirtied Blocks")),
            shared_written_blocks=_opt_int(node_dict.get("Shared Written Blocks")),
            temp_read_blocks=_opt_int(node_dict.get("Temp Read Blocks")),
            temp_written_blocks=_opt_int(node_dict.get("Temp Written Blocks")),
            sort_method=node_dict.get("Sort Method"),
            sort_space_used=_opt_int(node_dict.get("Sort Space Used")),
            sort_space_type=node_dict.get("Sort Space Type"),
            sort_key=_opt_list(node_dict.get("Sort Key")),
            group_key=_opt_list(node_dict.get("Group Key")),
            filter_cond=node_dict.get("Filter"),
            index_cond=node_dict.get("Index Cond"),
            hash_cond=node_dict.get("Hash Cond"),
            merge_cond=node_dict.get("Merge Cond"),
            recheck_cond=node_dict.get("Recheck Cond"),
            rows_removed_by_filter=_opt_int(node_dict.get("Rows Removed by Filter")),
            rows_removed_by_recheck=_opt_int(node_dict.get("Rows Removed by Index Recheck")),
            heap_fetches=_opt_int(node_dict.get("Heap Fetches")),
            workers_planned=_opt_int(node_dict.get("Workers Planned")),
            workers_launched=_opt_int(node_dict.get("Workers Launched")),
            parallel_aware=bool(node_dict.get("Parallel Aware", False)),
            subplan_name=node_dict.get("Subplan Name"),
            output_columns=_opt_list(node_dict.get("Output")),
        )
        all_nodes.append(node)

        raw_children = node_dict.get("Plans") or []
        if isinstance(raw_children, list):
            for child_dict in raw_children:
                if isinstance(child_dict, dict):
                    node.children.append(_walk(child_dict, depth + 1))

        # Exclusive (self) time calculation: subtract direct non-InitPlan children inclusive time
        if node.inclusive_time_ms is not None:
            child_sum = sum(
                c.inclusive_time_ms
                for c in node.children
                if c.inclusive_time_ms is not None and c.parent_relationship != "InitPlan"
            )
            node.self_time_ms = round(max(0.0, node.inclusive_time_ms - child_sum), 3)

        return node

    root = _walk(plan_root_dict, 0)
    analyzed = root.actual_total_time is not None

    used_indexes = sorted({n.index_name for n in all_nodes if n.index_name})
    node_types = [n.node_type for n in all_nodes]

    # Root node cumulative buffers in PG EXPLAIN (BUFFERS) include subtree buffers when available
    root_hit = root.shared_hit_blocks
    root_read = root.shared_read_blocks
    root_temp = root.temp_written_blocks

    return ParsedExplainPlan(
        root=root,
        analyzed=analyzed,
        planning_time_ms=_opt_float(envelope.get("Planning Time")),
        execution_time_ms=_opt_float(envelope.get("Execution Time")),
        total_cost=root.total_cost,
        root_plan_rows=root.plan_rows,
        root_actual_rows=root.actual_rows,
        total_shared_hit_blocks=root_hit,
        total_shared_read_blocks=root_read,
        total_temp_written_blocks=root_temp,
        used_indexes=used_indexes,
        node_types=node_types,
        all_nodes=all_nodes,
        raw_json=raw_json,
    )
