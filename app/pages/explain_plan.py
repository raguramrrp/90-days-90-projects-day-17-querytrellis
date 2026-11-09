"""Execution Plan Analyzer page for QueryTrellis."""
from __future__ import annotations

import streamlit as st

from app.components.plan_visualizer import render_explain_plan_panel
from app.components.topbar import render_topbar
from app.components.ui_primitives import render_empty_state, render_error_state
from app.state import navigate_to
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.services.workbench_service import FullAnalysisBundle, analyze_query_end_to_end


def render_explain_plan_page() -> None:
    """Render interactive PostgreSQL execution plan explorer, node inspector, and timing charts."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")
    active_sql = bundle.sql_text if (bundle and bundle.sql_text.strip()) else st.session_state.get("qt_editor_sql", "")

    def _trigger_top_analyze() -> None:
        st.session_state["qt_pending_explain_mode"] = "analyze"
        st.rerun()

    render_topbar(
        "Explain Plan",
        right_meta=(
            f"{len(bundle.parsed_plan.all_nodes)} nodes"
            if (bundle and bundle.parsed_plan)
            else "No active plan"
        ),
        action_label="Run EXPLAIN ANALYZE" if conn_mgr.is_connected else None,
        action_icon="play_arrow",
        on_action=_trigger_top_analyze if conn_mgr.is_connected else None,
    )

    pending_mode = st.session_state.pop("qt_pending_explain_mode", None)
    if pending_mode in ("analyze", "estimate") and conn_mgr.is_connected and active_sql.strip():
        use_analyze = pending_mode == "analyze"
        label = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)" if use_analyze else "EXPLAIN (FORMAT JSON)"
        with st.spinner(f"Running {label}..."):
            bundle = analyze_query_end_to_end(
                active_sql,
                conn_manager=conn_mgr,
                metadata_store=store,
                analyze_explain=use_analyze,
                buffers=use_analyze,
                timeout_ms=int(st.session_state.get("qt_timeout_ms", 5000)),
                persist=True,
            )
            st.session_state["qt_last_analysis"] = bundle
            st.session_state["qt_selected_plan_node_id"] = 0

    col_sql, col_b1, col_b2, col_b3 = st.columns([2.1, 0.95, 0.95, 0.8], vertical_alignment="top")
    with col_sql:
        with st.expander("Target SQL Statement", expanded=False):
            st.code(active_sql or "-- No SQL loaded", language="sql")

    with col_b1:
        if st.button(
            "EXPLAIN ANALYZE",
            key="qt_ep_btn_analyze",
            type="primary",
            width="stretch",
            disabled=not (conn_mgr.is_connected and active_sql.strip()),
        ):
            st.session_state["qt_pending_explain_mode"] = "analyze"
            st.rerun()

    with col_b2:
        if st.button(
            "EXPLAIN (Estimate Only)",
            key="qt_ep_btn_estimate",
            width="stretch",
            disabled=not (conn_mgr.is_connected and active_sql.strip()),
        ):
            st.session_state["qt_pending_explain_mode"] = "estimate"
            st.rerun()

    with col_b3:
        if st.button("Edit SQL", key="qt_ep_edit_sql", icon=":material/code:", width="stretch"):
            navigate_to("Query Editor")
            st.rerun()

    if bundle is None or bundle.parsed_plan is None:
        if bundle and bundle.error_message:
            render_error_state("Execution Plan Failed", bundle.error_message)
        elif not conn_mgr.is_connected:
            render_empty_state(
                "No Live Execution Plan Loaded",
                "Connect to PostgreSQL in Settings, then click Explain Analyze in Query Editor (or load a historical plan from Query History).",
                action_label="Open Settings",
                action_key="qt_ep_empty_settings",
                on_action=lambda: (navigate_to("Settings"), st.rerun()),
            )
        else:
            render_empty_state(
                "No Execution Plan Captured Yet",
                "Click EXPLAIN ANALYZE above to inspect PostgreSQL operators, timings, buffers, and row estimates.",
                action_label="Run EXPLAIN ANALYZE",
                action_key="qt_ep_empty_run",
                on_action=_trigger_top_analyze,
            )
        return

    render_explain_plan_panel(bundle.parsed_plan, bundle.plan_insights)
