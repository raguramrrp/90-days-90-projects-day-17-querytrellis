"""C. Explain Plan Inspector page."""
from __future__ import annotations

import streamlit as st

from app.components.plan_visualizer import render_explain_plan_panel
from app.components.sidebar import render_page_header
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.services.workbench_service import FullAnalysisBundle, analyze_query_end_to_end


def render_explain_plan_page() -> None:
    render_page_header(
        "Execution Plan Analyzer",
        "Inspect PostgreSQL EXPLAIN / EXPLAIN (ANALYZE, BUFFERS) trees, costs, cardinalities, and bottlenecks.",
    )

    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")

    col_info, col_btn1, col_btn2 = st.columns([2.2, 1.0, 1.0])
    with col_info:
        active_sql = bundle.sql_text if bundle else st.session_state.get("qt_editor_sql", "")
        with st.expander("Current Active SQL", expanded=False):
            st.code(active_sql or "-- No SQL loaded", language="sql")

    with col_btn1:
        if st.button("Run EXPLAIN ANALYZE", type="primary", width="stretch", disabled=not conn_mgr.is_connected):
            with st.spinner("Running EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)..."):
                bundle = analyze_query_end_to_end(
                    active_sql,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=True,
                    buffers=True,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                    persist=True,
                )
                st.session_state["qt_last_analysis"] = bundle

    with col_btn2:
        if st.button("Run EXPLAIN (Estimate Only)", width="stretch", disabled=not conn_mgr.is_connected):
            with st.spinner("Running EXPLAIN (FORMAT JSON)..."):
                bundle = analyze_query_end_to_end(
                    active_sql,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=False,
                    buffers=False,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                    persist=True,
                )
                st.session_state["qt_last_analysis"] = bundle

    if bundle is None or bundle.parsed_plan is None:
        if bundle and bundle.error_message:
            st.error(bundle.error_message)
        elif not conn_mgr.is_connected:
            st.info(
                "Connect to PostgreSQL in Settings and click 'Analyze Query' in the Query Editor to inspect live execution plans."
            )
        else:
            st.info("No execution plan captured yet. Click 'Run EXPLAIN ANALYZE' above or analyze a query from Query Editor.")
        return

    render_explain_plan_panel(bundle.parsed_plan, bundle.plan_insights)
