"""Interactive execution plan tree, node inspector, and theme-aware Plotly charts."""
from __future__ import annotations

import html
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.ui_primitives import (
    TelemetryCardData,
    render_section_header,
    render_severity_pill,
    render_telemetry_row,
)
from app.theme import ThemeTokens, apply_plotly_theme, get_active_theme
from src.explain.plan_analyzer import PlanInsight
from src.explain.plan_parser import ParsedExplainPlan, PlanNode


_NODE_OPERATOR_GUIDE: dict[str, str] = {
    "Seq Scan": (
        "Reads every live heap page of the table sequentially. Efficient for small tables or when reading a large "
        "fraction of rows; becomes expensive on large tables when a selective Filter discards most rows."
    ),
    "Index Scan": (
        "Traverses a B-tree (or other) index to locate matching tuple pointers and fetches corresponding columns "
        "from heap pages. Ideal for selective predicates; watch Heap/Buffer Reads and inner Nested Loop counts."
    ),
    "Index Only Scan": (
        "Satisfies both predicates and projected columns directly from the index leaf pages without visiting heap tuples "
        "for all-visible pages (tracked by Heap Fetches). Fastest selective access path when visibility map is clean."
    ),
    "Bitmap Index Scan": (
        "Scans an index to build an in-memory page/tuple bitmap rather than fetching heap pages one row at a time. "
        "Pairs with Bitmap Heap Scan so heap pages are visited sequentially."
    ),
    "Bitmap Heap Scan": (
        "Fetches heap pages identified by child Bitmap Index Scan(s) and rechecks conditions if work_mem forced lossy "
        "page-level bitmaps."
    ),
    "Hash Join": (
        "Builds an in-memory hash table on the smaller (Inner) relation, then probes it while streaming the Outer relation. "
        "Strong default for medium/large unindexed equi-joins; watch Temp Written Blocks if hash batches spill to disk."
    ),
    "Nested Loop": (
        "For every row from the Outer input, executes the Inner input. Fast when Outer yields few rows and Inner uses "
        "an indexed lookup; becomes quadratic if Outer row estimates are badly underestimated."
    ),
    "Merge Join": (
        "Joins two pre-sorted (or index-ordered) streams in a single pass. Performs well for large equi-joins when inputs "
        "can avoid an extra Sort or use existing index ordering."
    ),
    "Hash": (
        "Constructs the in-memory hash table consumed by a parent Hash Join node. High memory or multiple batches indicates "
        "a large build-side input exceeding hash_mem_multiplier * work_mem."
    ),
    "Sort": (
        "Orders incoming tuples by Sort Key before parent operators or final output. Check Sort Space Type: 'Memory' "
        "(quicksort/top-N heapsort) is fast, whereas 'Disk' (external merge) signals temp I/O bottlenecks."
    ),
    "Incremental Sort": (
        "Exploits a prefix of columns that are already presorted (e.g. from an index) and only sorts groups sharing "
        "identical prefix keys, reducing memory compared to a full Sort."
    ),
    "Aggregate": (
        "Computes GROUP BY or scalar aggregates. Uses Plain, Sorted (requires ordered input), or Hashed strategy depending "
        "on input ordering and estimated group cardinality."
    ),
    "HashAggregate": (
        "Groups and aggregates tuples via an in-memory hash table without presorting. Can spill to temporary disk batches "
        "when distinct group count exceeds work_mem."
    ),
    "GroupAggregate": (
        "Aggregates adjacent rows sharing grouping keys on an already-sorted input stream. Very low memory footprint."
    ),
    "WindowAgg": (
        "Evaluates OVER (...) window frame functions over partitions. Requires sorted partition/order keys from child node."
    ),
    "Gather": (
        "Collects tuple streams from parallel worker processes without preserving order. Compare Workers Planned vs Launched "
        "when parallelism appears lower than expected."
    ),
    "Gather Merge": (
        "Collects pre-sorted streams from parallel workers while maintaining sort order across workers."
    ),
    "Limit": (
        "Stops pulling rows from its child subtree once the requested row cap (and OFFSET) is satisfied. Large OFFSETs still "
        "force PostgreSQL to produce and discard skipped tuples."
    ),
    "Memoize": (
        "Caches recent Inner subtree results keyed by Nested Loop parameter values to avoid repeated index probes for duplicate keys."
    ),
    "Materialize": (
        "Stores child output in memory (or disk if large) so an inner join side can be rescanned without re-executing child nodes."
    ),
    "CTE Scan": (
        "Reads from a materialized Common Table Expression result buffer. Non-materialized CTEs are usually inlined by PostgreSQL 12+."
    ),
    "Subquery Scan": (
        "Wraps an optimized or standalone subquery block when planner boundaries prevent flattening into the outer query."
    ),
}


def _describe_node_type(node_type: str) -> str:
    return _NODE_OPERATOR_GUIDE.get(
        node_type,
        f"PostgreSQL '{node_type}' plan operator. Inspect Planner Estimates vs Actual Execution rows, loops, and buffers below to verify cost assumptions.",
    )


_TREE_CSS = """
.qt-ptree-shell {
    background: var(--pt-surface);
    border: 1px solid var(--pt-border-subtle);
    border-radius: 5px;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    color: var(--pt-fg);
    overflow: hidden;
}

.qt-ptree-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 10px;
    background: var(--pt-elev);
    border-bottom: 1px solid var(--pt-border-subtle);
}

.qt-ptree-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--pt-sec);
}

.qt-ptree-actions {
    display: flex;
    align-items: center;
    gap: 6px;
}

.qt-ptree-btn {
    appearance: none;
    cursor: pointer;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--pt-border);
    background: var(--pt-surface);
    color: var(--pt-sec);
    font-size: 11px;
    font-weight: 500;
    font-family: inherit;
}

.qt-ptree-btn:hover {
    border-color: var(--pt-accent);
    color: var(--pt-fg);
}

.qt-ptree-list {
    padding: 8px;
    max-height: 495px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.qt-pnode-row {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    padding: 7px 9px;
    border-radius: 4px;
    border: 1px solid var(--pt-border-subtle);
    border-left: 3px solid var(--pt-border);
    background: var(--pt-bg);
    cursor: pointer;
    transition: background-color 0.1s ease, border-color 0.1s ease;
}

.qt-pnode-row:hover {
    background: var(--pt-elev);
    border-color: var(--pt-border);
}

.qt-pnode-row.is-selected {
    background: var(--pt-accent-soft);
    border-color: var(--pt-accent);
    border-left-color: var(--pt-accent);
}

.qt-pnode-row.sev-High { border-left-color: var(--pt-err); }
.qt-pnode-row.sev-Medium { border-left-color: var(--pt-warn); }
.qt-pnode-row.sev-Low { border-left-color: var(--pt-info); }
.qt-pnode-row.is-selected.sev-High,
.qt-pnode-row.is-selected.sev-Medium,
.qt-pnode-row.is-selected.sev-Low { border-left-color: var(--pt-accent); }

.qt-pnode-toggle {
    width: 18px;
    height: 18px;
    min-width: 18px;
    border-radius: 3px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--pt-muted);
    font-size: 11px;
    line-height: 16px;
    text-align: center;
    padding: 0;
    cursor: pointer;
    margin-top: 1px;
}

.qt-pnode-toggle:hover {
    background: var(--pt-surface);
    border-color: var(--pt-border);
    color: var(--pt-fg);
}

.qt-pnode-spacer {
    width: 18px;
    min-width: 18px;
    height: 18px;
}

.qt-pnode-main {
    flex: 1 1 auto;
    min-width: 0;
}

.qt-pnode-top {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px;
}

.qt-pnode-id {
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 11px;
    color: var(--pt-muted);
}

.qt-pnode-type {
    font-size: 12px;
    font-weight: 600;
    color: var(--pt-fg);
}

.qt-pnode-target {
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 11px;
    color: var(--pt-accent-text);
}

.qt-pnode-rel {
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 3px;
    background: var(--pt-surface);
    border: 1px solid var(--pt-border-subtle);
    color: var(--pt-muted);
    text-transform: uppercase;
}

.qt-pnode-sev {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 3px;
}
.qt-pnode-sev-High { background: var(--pt-err-bg); color: var(--pt-err); }
.qt-pnode-sev-Medium { background: var(--pt-warn-bg); color: var(--pt-warn); }
.qt-pnode-sev-Low { background: var(--pt-info-bg); color: var(--pt-info); }

.qt-pnode-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 3px;
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 11px;
    color: var(--pt-sec);
}
"""

_TREE_JS = """
function esc(s) {
    return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

export default function(component) {
    const { data, setTriggerValue, parentElement } = component;
    if (!data) return;

    let shell = parentElement.querySelector(".qt-ptree-shell");
    if (!shell) {
        shell = document.createElement("div");
        shell.className = "qt-ptree-shell";
        shell.innerHTML = `
            <div class="qt-ptree-head">
                <span class="qt-ptree-title">Execution Plan Hierarchy</span>
                <div class="qt-ptree-actions">
                    <button type="button" class="qt-ptree-btn" data-tree-act="expand">Expand All</button>
                    <button type="button" class="qt-ptree-btn" data-tree-act="collapse">Collapse Subtrees</button>
                </div>
            </div>
            <div class="qt-ptree-list"></div>
        `;
        parentElement.appendChild(shell);
        shell._collapsedIds = new Set();
        shell._nonce = 0;

        shell.querySelector('[data-tree-act="expand"]').addEventListener("click", () => {
            shell._collapsedIds.clear();
            renderTreeNodes(shell);
        });
        shell.querySelector('[data-tree-act="collapse"]').addEventListener("click", () => {
            const nodes = shell._lastData?.nodes || [];
            shell._collapsedIds = new Set(nodes.filter(n => n.hasChildren && n.depth > 0).map(n => n.id));
            renderTreeNodes(shell);
        });
    }

    const pal = data.palette || {};
    shell.style.setProperty("--pt-bg", pal.bg || "#151C24");
    shell.style.setProperty("--pt-surface", pal.surface || "#1B2530");
    shell.style.setProperty("--pt-elev", pal.elev || "#202C38");
    shell.style.setProperty("--pt-border", pal.border || "#34414D");
    shell.style.setProperty("--pt-border-subtle", pal.borderSubtle || "#25313D");
    shell.style.setProperty("--pt-fg", pal.fg || "#E8EDF2");
    shell.style.setProperty("--pt-sec", pal.sec || "#9BA9B7");
    shell.style.setProperty("--pt-muted", pal.muted || "#738292");
    shell.style.setProperty("--pt-accent", pal.accent || "#35A99B");
    shell.style.setProperty("--pt-accent-soft", pal.accentSoft || "rgba(53,169,155,0.14)");
    shell.style.setProperty("--pt-accent-text", pal.accentText || "#58C4B6");
    shell.style.setProperty("--pt-err", pal.err || "#CE5C5C");
    shell.style.setProperty("--pt-err-bg", pal.errBg || "rgba(206,92,92,0.15)");
    shell.style.setProperty("--pt-warn", pal.warn || "#C88D3B");
    shell.style.setProperty("--pt-warn-bg", pal.warnBg || "rgba(200,141,59,0.14)");
    shell.style.setProperty("--pt-info", pal.info || "#5495C7");
    shell.style.setProperty("--pt-info-bg", pal.infoBg || "rgba(84,149,199,0.14)");

    if (shell._lastPlanSig !== data.planSig) {
        shell._collapsedIds.clear();
        shell._lastPlanSig = data.planSig;
    }

    shell._lastData = data;
    shell._setTriggerValue = setTriggerValue;
    renderTreeNodes(shell);
}

function renderTreeNodes(shell) {
    const data = shell._lastData;
    const listEl = shell.querySelector(".qt-ptree-list");
    const nodes = data.nodes || [];
    const selectedId = Number(data.selectedId ?? 0);
    const collapsed = shell._collapsedIds;

    // Determine visible nodes by skipping descendants of collapsed parents
    let skipDepth = null;
    const visible = [];
    for (const n of nodes) {
        if (skipDepth !== null && n.depth > skipDepth) {
            continue;
        }
        skipDepth = null;
        visible.push(n);
        if (n.hasChildren && collapsed.has(n.id)) {
            skipDepth = n.depth;
        }
    }

    listEl.innerHTML = visible.map((n) => {
        const isSel = n.id === selectedId;
        const isCol = collapsed.has(n.id);
        const padPx = 8 + Math.min(n.depth, 9) * 16;
        const sevCls = n.severity ? " sev-" + n.severity : "";
        const selCls = isSel ? " is-selected" : "";
        const toggleHtml = n.hasChildren
            ? `<button type="button" class="qt-pnode-toggle" data-toggle-id="${n.id}" title="${isCol ? "Expand children" : "Collapse children"}">${isCol ? "&#9656;" : "&#9662;"}</button>`
            : `<span class="qt-pnode-spacer"></span>`;
        const relHtml = n.rel ? `<span class="qt-pnode-rel">${esc(n.rel)}</span>` : "";
        const targetHtml = n.target ? `<span class="qt-pnode-target">${esc(n.target)}</span>` : "";
        const sevBadge = n.severity ? `<span class="qt-pnode-sev qt-pnode-sev-${n.severity}">${esc(n.severity)}</span>` : "";
        const metaSpans = (n.meta || []).map(m => `<span>${esc(m)}</span>`).join("");

        return `
            <div class="qt-pnode-row${selCls}${sevCls}" data-node-id="${n.id}" style="margin-left:${Math.min(n.depth, 9) * 12}px;">
                ${toggleHtml}
                <div class="qt-pnode-main">
                    <div class="qt-pnode-top">
                        <span class="qt-pnode-id">#${n.id}</span>
                        ${relHtml}
                        <span class="qt-pnode-type">${esc(n.nodeType)}</span>
                        ${targetHtml}
                        ${sevBadge}
                    </div>
                    <div class="qt-pnode-meta">${metaSpans}</div>
                </div>
            </div>
        `;
    }).join("");

    listEl.querySelectorAll(".qt-pnode-toggle").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const nid = Number(btn.getAttribute("data-toggle-id"));
            if (shell._collapsedIds.has(nid)) {
                shell._collapsedIds.delete(nid);
            } else {
                shell._collapsedIds.add(nid);
            }
            renderTreeNodes(shell);
        });
    });

    listEl.querySelectorAll(".qt-pnode-row").forEach((row) => {
        row.addEventListener("click", () => {
            const nid = Number(row.getAttribute("data-node-id"));
            listEl.querySelectorAll(".qt-pnode-row").forEach(r => r.classList.remove("is-selected"));
            row.classList.add("is-selected");
            shell._nonce += 1;
            shell._setTriggerValue("selection", { nodeId: nid, nonce: shell._nonce });
        });
    });
}
"""

_PLAN_TREE_COMPONENT = st.components.v2.component(
    "qt_explain_plan_tree",
    css=_TREE_CSS,
    js=_TREE_JS,
)


def _node_target_label(n: PlanNode) -> str:
    target = n.relation_name or n.alias
    if target and n.index_name:
        return f"on {target} using {n.index_name}"
    if target:
        return f"on {target}"
    if n.index_name:
        return f"using {n.index_name}"
    return ""


def _highest_node_severity(node_id: int, insights: list[PlanInsight]) -> str | None:
    rank = {"High": 3, "Medium": 2, "Low": 1, "Info": 0}
    best: str | None = None
    best_r = 0
    for ins in insights:
        if ins.node_id == node_id:
            r = rank.get(ins.severity, 0)
            if r > best_r:
                best_r = r
                best = ins.severity
    return best


def _serialize_plan_nodes(plan: ParsedExplainPlan, insights: list[PlanInsight]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for n in plan.all_nodes:
        meta: list[str] = []
        if plan.analyzed and n.self_time_ms is not None:
            meta.append(f"self {n.self_time_ms:.2f} ms")
        if plan.analyzed and n.inclusive_time_ms is not None:
            meta.append(f"total {n.inclusive_time_ms:.2f} ms")
        if n.total_cost is not None:
            meta.append(f"cost {n.total_cost:,.1f}")
        if plan.analyzed and n.actual_rows is not None:
            est_txt = f"{n.plan_rows:,}" if n.plan_rows is not None else "?"
            meta.append(f"rows {n.actual_rows:,} (est {est_txt})")
        elif n.plan_rows is not None:
            meta.append(f"est rows {n.plan_rows:,}")
        if plan.analyzed and n.actual_loops is not None and n.actual_loops > 1:
            meta.append(f"loops {n.actual_loops:,}")

        serialized.append(
            {
                "id": n.node_id,
                "depth": n.depth,
                "nodeType": (f"{n.join_type} {n.node_type}" if n.join_type and n.join_type not in n.node_type else n.node_type),
                "target": _node_target_label(n),
                "rel": n.parent_relationship or "",
                "hasChildren": bool(n.children),
                "severity": _highest_node_severity(n.node_id, insights),
                "meta": meta,
            }
        )
    return serialized


def build_node_time_chart(plan: ParsedExplainPlan, theme: ThemeTokens | None = None) -> go.Figure:
    """Create a horizontal Plotly bar chart of exclusive self-time (or estimated cost)."""
    t = theme or get_active_theme()
    nodes = list(reversed(plan.all_nodes))
    labels = [f"#{n.node_id} {n.label[:40]}" for n in nodes]

    if plan.analyzed:
        vals = [n.self_time_ms or 0.0 for n in nodes]
        x_title = "Exclusive Self Time (ms)"
        title = "Execution Time Breakdown by Node (Self Time)"
        color = t.accent
    else:
        vals = [n.total_cost or 0.0 for n in nodes]
        x_title = "Estimated Cumulative Cost"
        title = "Estimated Planner Cost by Node (Estimate Only)"
        color = t.info

    fig = go.Figure(
        go.Bar(
            x=vals,
            y=labels,
            orientation="h",
            marker_color=color,
            text=[f"{v:.2f}" for v in vals],
            textposition="auto",
        )
    )
    fig.update_xaxes(title_text=x_title)
    fig.update_yaxes(title_text="")
    return apply_plotly_theme(
        fig,
        t,
        height=max(260, min(520, 38 * len(nodes) + 84)),
        title=title,
        show_legend=False,
    )


def build_rows_comparison_chart(plan: ParsedExplainPlan, theme: ThemeTokens | None = None) -> go.Figure:
    """Create a grouped bar chart comparing Planner Estimated Rows vs. Actual Rows."""
    t = theme or get_active_theme()
    nodes = [n for n in plan.all_nodes if n.plan_rows is not None]
    labels = [f"#{n.node_id} {n.node_type}" for n in nodes]
    est = [n.plan_rows or 0 for n in nodes]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(name="Planner Estimate", x=labels, y=est, marker_color=t.bar_secondary)
    )
    if plan.analyzed:
        act = [n.actual_rows if n.actual_rows is not None else 0 for n in nodes]
        fig.add_trace(
            go.Bar(name="Actual Rows", x=labels, y=act, marker_color=t.accent)
        )

    fig.update_layout(barmode="group")
    fig.update_xaxes(title_text="Plan Node")
    fig.update_yaxes(title_text="Row Count")
    return apply_plotly_theme(
        fig,
        t,
        height=max(260, min(420, 310)),
        title="Estimated vs. Actual Rows per Node",
        margin={"l": 12, "r": 16, "t": 64, "b": 42},
        show_legend=True,
    )


def _render_kv_table(rows: list[tuple[str, str]]) -> None:
    esc = html.escape
    trs = "".join(
        f"<tr><td style='width:42%;color:var(--qt-text-secondary);font-size:0.77rem;'>{esc(k)}</td>"
        f"<td class='qt-mono' style='font-size:0.78rem;word-break:break-word;'>{esc(v)}</td></tr>"
        for k, v in rows
    )
    st.markdown(
        f"<div class='qt-table-wrap'><table class='qt-table'><tbody>{trs}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _render_node_inspector(sel_node: PlanNode, plan: ParsedExplainPlan, insights: list[PlanInsight]) -> None:
    esc = html.escape
    node_insights = [ins for ins in insights if ins.node_id == sel_node.node_id]
    sev_badges = "".join(render_severity_pill(ins.severity) for ins in node_insights)

    target_str = _node_target_label(sel_node) or "No target relation"
    st.markdown(
        f"""
        <div class="qt-surface-card">
            <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;">
                <div>
                    <span class="qt-pill qt-pill-accent">Node #{sel_node.node_id} &middot; Depth {sel_node.depth}</span>
                    <span style="font-weight:700;font-size:0.96rem;margin-left:6px;color:var(--qt-text-primary);">{esc(sel_node.node_type)}</span>
                    <span class="qt-mono" style="font-size:0.80rem;color:var(--qt-text-secondary);margin-left:6px;">{esc(target_str)}</span>
                </div>
                <div style="display:flex;gap:4px;">{sev_badges}</div>
            </div>
            <div style="font-size:0.79rem;color:var(--qt-text-secondary);line-height:1.45;">
                {esc(_describe_node_type(sel_node.node_type))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_est, col_act = st.columns(2)
    with col_est:
        st.markdown(
            "<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--qt-text-muted);margin:6px 0 4px 0;'>Planner Estimates</div>",
            unsafe_allow_html=True,
        )
        est_rows = [
            ("Estimated Rows", f"{sel_node.plan_rows:,}" if sel_node.plan_rows is not None else "Unavailable"),
            ("Startup / Total Cost", f"{sel_node.startup_cost:.2f} .. {sel_node.total_cost:.2f}" if sel_node.total_cost is not None and sel_node.startup_cost is not None else "Unavailable"),
            ("Row Width (Bytes)", f"{sel_node.plan_width} B" if sel_node.plan_width is not None else "Unavailable"),
            ("Estimation Factor", f"{sel_node.estimation_factor}x" if sel_node.estimation_factor is not None else "Unavailable"),
            ("Index Condition", sel_node.index_cond or "None"),
            ("Filter Predicate", sel_node.filter_cond or "None"),
            ("Join Condition", sel_node.hash_cond or sel_node.merge_cond or "None"),
        ]
        _render_kv_table(est_rows)

    with col_act:
        st.markdown(
            "<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--qt-text-muted);margin:6px 0 4px 0;'>Actual Execution Statistics</div>",
            unsafe_allow_html=True,
        )
        analyzed = plan.analyzed
        act_rows = [
            ("Actual Rows", f"{sel_node.actual_rows:,}" if analyzed and sel_node.actual_rows is not None else "Unavailable"),
            ("Actual Loops", f"{sel_node.actual_loops:,}" if analyzed and sel_node.actual_loops is not None else "Unavailable"),
            ("Exclusive Self Time", f"{sel_node.self_time_ms:.3f} ms" if analyzed and sel_node.self_time_ms is not None else "Unavailable"),
            ("Inclusive Subtree Time", f"{sel_node.inclusive_time_ms:.3f} ms" if analyzed and sel_node.inclusive_time_ms is not None else "Unavailable"),
            ("Rows Removed by Filter", f"{sel_node.rows_removed_by_filter:,}" if sel_node.rows_removed_by_filter is not None else "Unavailable"),
            (
                "Shared Buffers (Hit / Read)",
                f"{sel_node.shared_hit_blocks:,} / {sel_node.shared_read_blocks:,}"
                if sel_node.shared_hit_blocks is not None and sel_node.shared_read_blocks is not None
                else "Unavailable",
            ),
            (
                "Sort / Temp Spill",
                (
                    f"{sel_node.sort_method} ({sel_node.sort_space_type or 'N/A'}, {sel_node.sort_space_used or 0} kB)"
                    if sel_node.sort_method
                    else (
                        f"Temp Written: {sel_node.temp_written_blocks:,} blocks"
                        if sel_node.temp_written_blocks
                        else "None"
                    )
                ),
            ),
        ]
        if sel_node.workers_planned is not None:
            act_rows.append(("Parallel Workers", f"{sel_node.workers_launched or 0} / {sel_node.workers_planned} planned"))
        _render_kv_table(act_rows)

    if node_insights:
        st.markdown(
            "<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--qt-text-muted);margin:8px 0 4px 0;'>Diagnostics for This Node</div>",
            unsafe_allow_html=True,
        )
        for ins in node_insights:
            banner_cls = "qt-banner qt-banner-err" if ins.severity == "High" else ("qt-banner qt-banner-warn" if ins.severity == "Medium" else "qt-banner")
            st.markdown(
                f"<div class='{banner_cls}' style='margin-bottom:5px;'>"
                f"<strong>[{esc(ins.severity)}] {esc(ins.title)}:</strong> {esc(ins.observation)}<br/>"
                f"<span style='color:var(--qt-text-secondary);'><em>Interpretation:</em> {esc(ins.interpretation)} &bull; <em>Action:</em> {esc(ins.recommendation)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


def render_explain_plan_panel(
    plan: ParsedExplainPlan,
    insights: list[PlanInsight],
    *,
    component_key: str = "qt_explain_tree_widget",
) -> None:
    """Render telemetry strip, interactive Left Tree + Right Node Inspector, and bottom charts/metrics."""
    theme = get_active_theme()

    cards = [
        TelemetryCardData(
            label="PG Execution Time",
            value=f"{plan.execution_time_ms:.3f} ms" if plan.execution_time_ms is not None else "Unavailable",
            subtext="Server-side EXPLAIN ANALYZE" if plan.analyzed else "Estimate-only EXPLAIN",
            accent=True,
            tone="ok" if plan.analyzed else "neutral",
        ),
        TelemetryCardData(
            label="PG Planning Time",
            value=f"{plan.planning_time_ms:.3f} ms" if plan.planning_time_ms is not None else "Unavailable",
            subtext="Planner optimization time",
        ),
        TelemetryCardData(
            label="Estimated Total Cost",
            value=f"{plan.total_cost:,.2f}" if plan.total_cost is not None else "Unavailable",
            subtext=f"{len(plan.all_nodes)} plan node(s) total",
        ),
        TelemetryCardData(
            label="Root Rows (Act / Est)",
            value=(
                f"{plan.root_actual_rows:,} / {plan.root_plan_rows:,}"
                if plan.root_actual_rows is not None and plan.root_plan_rows is not None
                else (f"Est: {plan.root_plan_rows:,}" if plan.root_plan_rows is not None else "Unavailable")
            ),
            subtext=f"Indexes: {len(plan.used_indexes)}" if plan.used_indexes else "No index scans in plan",
        ),
        TelemetryCardData(
            label="Shared Buffers (Hit / Read)",
            value=(
                f"{plan.total_shared_hit_blocks or 0:,} / {plan.total_shared_read_blocks or 0:,}"
                if plan.total_shared_hit_blocks is not None or plan.total_shared_read_blocks is not None
                else "Unavailable"
            ),
            subtext="8 KB pages cache vs OS/disk",
        ),
    ]
    render_telemetry_row(cards)

    if not plan.analyzed:
        st.markdown(
            "<div class='qt-banner'>"
            "<strong>Estimate-Only Plan Mode:</strong> Actual Time, Actual Rows, Loops, and Buffer Hits/Reads are "
            "explicitly shown as <strong>Unavailable</strong> until you run <strong>Run EXPLAIN ANALYZE</strong>."
            "</div>",
            unsafe_allow_html=True,
        )

    valid_ids = {n.node_id for n in plan.all_nodes}
    selected_id = int(st.session_state.get("qt_selected_plan_node_id", 0))
    if selected_id not in valid_ids:
        selected_id = 0
        st.session_state["qt_selected_plan_node_id"] = 0

    plan_sig = f"{len(plan.all_nodes)}:{plan.total_cost}:{plan.execution_time_ms}:{plan.root.node_type}"
    serialized_nodes = _serialize_plan_nodes(plan, insights)

    render_section_header(
        "Execution Plan Hierarchy & Selected Node Inspector",
        f"{'ANALYZE + BUFFERS' if plan.analyzed else 'ESTIMATE ONLY'} | Click any node on the left to inspect",
    )

    col_tree, col_insp = st.columns([1.05, 1.35], gap="medium")
    with col_tree:
        tree_res = _PLAN_TREE_COMPONENT(
            key=component_key,
            data={
                "planSig": plan_sig,
                "selectedId": selected_id,
                "nodes": serialized_nodes,
                "palette": {
                    "bg": theme.bg_app,
                    "surface": theme.bg_surface,
                    "elev": theme.bg_elevated,
                    "border": theme.border,
                    "borderSubtle": theme.border_subtle,
                    "fg": theme.text_primary,
                    "sec": theme.text_secondary,
                    "muted": theme.text_muted,
                    "accent": theme.accent,
                    "accentSoft": theme.accent_soft,
                    "accentText": theme.accent_text,
                    "err": theme.error,
                    "errBg": theme.error_bg,
                    "warn": theme.warning,
                    "warnBg": theme.warning_bg,
                    "info": theme.info,
                    "infoBg": theme.info_bg,
                },
            },
            on_selection_change=lambda: None,
        )
        sel_evt = getattr(tree_res, "selection", None)
        if isinstance(sel_evt, dict):
            evt_sig = f"{plan_sig}:{sel_evt.get('nonce')}"
            if evt_sig != st.session_state.get("qt_last_plan_click_sig"):
                st.session_state["qt_last_plan_click_sig"] = evt_sig
                cand_id = int(sel_evt.get("nodeId", 0))
                if cand_id in valid_ids:
                    selected_id = cand_id
                    st.session_state["qt_selected_plan_node_id"] = selected_id

    sel_node = next((n for n in plan.all_nodes if n.node_id == selected_id), plan.root)
    with col_insp:
        _render_node_inspector(sel_node, plan, insights)

    render_section_header("Plan Timing & Cardinality Distribution", f"{len(plan.all_nodes)} plan node(s)")
    c_left, c_right = st.columns(2)
    with c_left:
        st.plotly_chart(build_node_time_chart(plan, theme), width="stretch")
    with c_right:
        st.plotly_chart(build_rows_comparison_chart(plan, theme), width="stretch")

    render_section_header("Node Execution Metrics Matrix")
    rows = []
    for n in plan.all_nodes:
        rows.append(
            {
                "ID": n.node_id,
                "Depth": n.depth,
                "Node": ("  " * n.depth) + n.label,
                "Est Cost": n.total_cost,
                "Est Rows": n.plan_rows,
                "Actual Rows": n.actual_rows if n.actual_rows is not None else "Unavailable",
                "Est Diff (x)": n.estimation_factor if n.estimation_factor is not None else "Unavailable",
                "Actual Time/Loop (ms)": n.actual_total_time if n.actual_total_time is not None else "Unavailable",
                "Loops": n.actual_loops if n.actual_loops is not None else "Unavailable",
                "Self Time (ms)": n.self_time_ms if n.self_time_ms is not None else "Unavailable",
                "Buf Hit": n.shared_hit_blocks if n.shared_hit_blocks is not None else "Unavailable",
                "Buf Read": n.shared_read_blocks if n.shared_read_blocks is not None else "Unavailable",
                "Filter Removed": n.rows_removed_by_filter if n.rows_removed_by_filter is not None else "-",
                "Sort": f"{n.sort_method} ({n.sort_space_type})" if n.sort_method else "-",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    render_section_header("Plan Diagnostic Findings", f"{len(insights)} insight(s)")
    if not insights:
        st.markdown(
            "<div class='qt-banner'>No notable execution plan bottlenecks were flagged for this plan.</div>",
            unsafe_allow_html=True,
        )
    else:
        for ins in insights:
            bcls = "qt-banner qt-banner-err" if ins.severity == "High" else ("qt-banner qt-banner-warn" if ins.severity == "Medium" else "qt-banner")
            st.markdown(
                f"<div class='{bcls}' style='margin-bottom:6px;'>"
                f"<strong>[{html.escape(ins.severity)}] Node #{ins.node_id} &middot; {html.escape(ins.title)} ({html.escape(ins.node_label)})</strong><br/>"
                f"{html.escape(ins.observation)}<br/>"
                f"<span style='color:var(--qt-text-secondary);'><em>Interpretation:</em> {html.escape(ins.interpretation)} &bull; "
                f"<em>Recommendation:</em> {html.escape(ins.recommendation)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    c_txt, c_json = st.columns(2)
    with c_txt:
        with st.expander("Text EXPLAIN Output", expanded=False):
            st.code(plan.to_text_tree(), language="text")
    with c_json:
        with st.expander("Raw PostgreSQL EXPLAIN (FORMAT JSON)", expanded=False):
            st.json(plan.raw_json)
