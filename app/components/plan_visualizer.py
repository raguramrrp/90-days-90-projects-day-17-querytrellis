"""Execution plan tree, Plotly node timing/cardinality charts, and node inspector."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.explain.plan_analyzer import PlanInsight
from src.explain.plan_parser import ParsedExplainPlan, PlanNode


def build_node_time_chart(plan: ParsedExplainPlan) -> go.Figure:
    """Create a horizontal Plotly bar chart of exclusive self-time (or total cost)."""
    nodes = list(reversed(plan.all_nodes))
    labels = [f"#{n.node_id} {n.label[:42]}" for n in nodes]

    if plan.analyzed:
        vals = [n.self_time_ms or 0.0 for n in nodes]
        x_title = "Exclusive Self Time (ms)"
        title = "Execution Time Breakdown by Plan Node (Self Time)"
        color = "#0F766E"
    else:
        vals = [n.total_cost or 0.0 for n in nodes]
        x_title = "Estimated Cumulative Cost"
        title = "Estimated Planner Cost by Plan Node (Estimate Only)"
        color = "#0369A1"

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
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title="",
        height=max(280, min(560, 42 * len(nodes) + 90)),
        margin=dict(l=10, r=20, t=40, b=35),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8FAFC",
        font=dict(color="#0F172A", size=12),
    )
    return fig


def build_rows_comparison_chart(plan: ParsedExplainPlan) -> go.Figure:
    """Create a grouped bar chart comparing Estimated Rows vs Actual Rows."""
    nodes = [n for n in plan.all_nodes if n.plan_rows is not None]
    labels = [f"#{n.node_id} {n.node_type}" for n in nodes]
    est = [n.plan_rows or 0 for n in nodes]
    act = [n.actual_rows if n.actual_rows is not None else 0 for n in nodes]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(name="Estimated Rows", x=labels, y=est, marker_color="#94A3B8")
    )
    if plan.analyzed:
        fig.add_trace(
            go.Bar(name="Actual Rows", x=labels, y=act, marker_color="#0F766E")
        )

    fig.update_layout(
        title=dict(text="Estimated vs. Actual Rows per Plan Node", y=0.96),
        barmode="group",
        xaxis_title="Plan Node",
        yaxis_title="Row Count",
        height=330,
        margin=dict(l=10, r=20, t=68, b=40),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8FAFC",
        font=dict(color="#0F172A", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
    )
    return fig


def render_explain_plan_panel(
    plan: ParsedExplainPlan,
    insights: list[PlanInsight],
) -> None:
    """Render full PostgreSQL execution plan tree, charts, node inspector, and bottlenecks."""
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "PG Execution Time",
        f"{plan.execution_time_ms:.3f} ms" if plan.execution_time_ms is not None else "Unavailable",
    )
    c2.metric(
        "PG Planning Time",
        f"{plan.planning_time_ms:.3f} ms" if plan.planning_time_ms is not None else "Unavailable",
    )
    c3.metric(
        "Estimated Total Cost",
        f"{plan.total_cost:,.2f}" if plan.total_cost is not None else "Unavailable",
    )
    c4.metric(
        "Root Rows (Act / Est)",
        (
            f"{plan.root_actual_rows:,} / {plan.root_plan_rows:,}"
            if plan.root_actual_rows is not None and plan.root_plan_rows is not None
            else (f"Est: {plan.root_plan_rows:,}" if plan.root_plan_rows is not None else "Unavailable")
        ),
    )
    c5.metric(
        "Shared Buffers (Hit / Read)",
        (
            f"{plan.total_shared_hit_blocks or 0:,} / {plan.total_shared_read_blocks or 0:,}"
            if plan.total_shared_hit_blocks is not None or plan.total_shared_read_blocks is not None
            else "Unavailable"
        ),
    )

    if not plan.analyzed:
        st.info(
            "Estimate-only EXPLAIN plan shown. Actual Time, Actual Rows, Loops, and Buffer Hits/Reads are marked Unavailable."
        )

    tab_tree, tab_table, tab_charts, tab_inspector = st.tabs(
        ["Execution Plan Tree", "Node Metrics Table", "Visual Charts", "Node Inspector"]
    )

    with tab_tree:
        st.code(plan.to_text_tree(), language="text")

    with tab_table:
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

    with tab_charts:
        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(build_node_time_chart(plan), width="stretch")
        with col_r:
            st.plotly_chart(build_rows_comparison_chart(plan), width="stretch")

    with tab_inspector:
        node_options = {f"#{n.node_id} — {n.label}": n for n in plan.all_nodes}
        chosen_label = st.selectbox("Select Plan Node", options=list(node_options.keys()))
        sel_node: PlanNode = node_options[chosen_label]

        d1, d2 = st.columns(2)
        with d1:
            st.markdown(f"**Node Type:** `{sel_node.node_type}`")
            st.markdown(f"**Relation / Alias:** `{sel_node.relation_name or 'N/A'}` (`{sel_node.alias or '-'}`)")
            st.markdown(f"**Index Name:** `{sel_node.index_name or 'None'}`")
            st.markdown(f"**Startup / Total Cost:** `{sel_node.startup_cost}` .. `{sel_node.total_cost}`")
            st.markdown(
                f"**Estimated vs Actual Rows:** `{sel_node.plan_rows}` vs "
                f"`{sel_node.actual_rows if sel_node.actual_rows is not None else 'Unavailable'}`"
            )
            st.markdown(
                f"**Loops / Self Time:** `{sel_node.actual_loops if sel_node.actual_loops is not None else 'Unavailable'}` / "
                f"`{f'{sel_node.self_time_ms} ms' if sel_node.self_time_ms is not None else 'Unavailable'}`"
            )
        with d2:
            st.markdown(f"**Index Cond:** `{sel_node.index_cond or 'None'}`")
            st.markdown(f"**Filter:** `{sel_node.filter_cond or 'None'}`")
            st.markdown(f"**Hash / Merge Cond:** `{sel_node.hash_cond or sel_node.merge_cond or 'None'}`")
            st.markdown(
                f"**Sort Details:** `{sel_node.sort_method or 'N/A'}` "
                f"(`{sel_node.sort_space_type or 'N/A'}`, `{sel_node.sort_space_used or 0} kB`)"
            )
            st.markdown(
                f"**Buffers (Hit / Read / Temp Written):** "
                f"`{sel_node.shared_hit_blocks if sel_node.shared_hit_blocks is not None else 'Unavailable'}` / "
                f"`{sel_node.shared_read_blocks if sel_node.shared_read_blocks is not None else 'Unavailable'}` / "
                f"`{sel_node.temp_written_blocks if sel_node.temp_written_blocks is not None else 0}`"
            )
            if sel_node.workers_planned is not None:
                st.markdown(
                    f"**Parallel Workers (Planned / Launched):** `{sel_node.workers_planned}` / `{sel_node.workers_launched}`"
                )

    st.subheader("Plan Diagnostics & Bottleneck Highlights")
    if not insights:
        st.success("No notable plan bottlenecks were flagged for this execution plan.")
    else:
        for ins in insights:
            with st.expander(f"[{ins.severity}] {ins.title} — {ins.node_label}", expanded=(ins.severity in ("High", "Medium"))):
                st.markdown(f"**Observation:** {ins.observation}")
                st.markdown(f"**Interpretation:** {ins.interpretation}")
                st.markdown(f"**Recommendation:** {ins.recommendation}")

    with st.expander("Raw PostgreSQL EXPLAIN (FORMAT JSON)", expanded=False):
        st.json(plan.raw_json)
