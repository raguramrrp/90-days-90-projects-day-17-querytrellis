"""G. Reports Export page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.sidebar import render_page_header
from app.state import load_history_record_into_state
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.reporting.report_generator import (
    build_benchmark_csv,
    build_html_report,
    build_json_report,
    build_plan_nodes_csv,
)
from src.services.workbench_service import FullAnalysisBundle


def render_reports_page() -> None:
    render_page_header(
        "Optimization Reports",
        "Generate sanitized, downloadable HTML, JSON, and CSV reports (credentials are never included).",
    )

    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]

    history_rows = store.list_analyses(limit=50, status_filter="success")
    source_options = ["Current Active Session Analysis"] + [
        f"History #{r['id']} ({r['created_at']}) — {(r['sql_text'] or '').splitlines()[0][:50]}"
        for r in history_rows
    ]
    chosen_src = st.selectbox("Report Source", options=source_options)
    if chosen_src != "Current Active Session Analysis":
        chosen_id = int(chosen_src.split("#", 1)[1].split(" ", 1)[0])
        if st.button("Load Selected Analysis for Report"):
            rec = store.get_analysis(chosen_id)
            if rec:
                load_history_record_into_state(rec)
                st.rerun()

    bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")
    benchmark = st.session_state.get("qt_last_benchmark")
    comparison = st.session_state.get("qt_last_comparison")

    if bundle is None:
        st.info(
            "No active query analysis in session. Analyze a query in Query Editor or select a historical record above."
        )
        return

    c_title, c_notes = st.columns([1.2, 1.8])
    report_title = c_title.text_input(
        "Report Title",
        value=f"QueryTrellis Optimization Report (Analysis #{bundle.analysis_id or 'Session'})",
    )
    opt_notes = c_notes.text_area(
        "Engineering Notes (Optional)",
        value="Generated via QueryTrellis local workbench.",
        height=90,
    )

    status = conn_mgr.status
    html_str = build_html_report(
        title=report_title,
        sql_text=bundle.sql_text,
        formatted_sql=bundle.formatted_sql,
        connection_info=(
            status.config
            if status.connected
            else {"database": "offline_static", "host": "N/A", "port": "N/A", "username": "N/A"}
        ),
        server_version=status.server_version,
        plan=bundle.parsed_plan,
        plan_insights=bundle.plan_insights,
        antipatterns=bundle.antipatterns,
        index_recommendations=bundle.index_recommendations,
        benchmark=benchmark,
        comparison=comparison,
        optimization_notes=opt_notes,
    )
    json_str = build_json_report(
        title=report_title,
        sql_text=bundle.sql_text,
        formatted_sql=bundle.formatted_sql,
        connection_info=status.config if status.connected else {"database": "offline_static"},
        server_version=status.server_version,
        plan=bundle.parsed_plan,
        plan_insights=bundle.plan_insights,
        antipatterns=bundle.antipatterns,
        index_recommendations=bundle.index_recommendations,
        benchmark=benchmark,
        comparison=comparison,
        optimization_notes=opt_notes,
    )

    db_label = status.current_database if status.connected else "offline"

    d1, d2, d3, d4 = st.columns(4)
    if d1.download_button(
        "Download HTML Report",
        data=html_str.encode("utf-8"),
        file_name="querytrellis_report.html",
        mime="text/html",
        type="primary",
        width="stretch",
    ):
        store.save_report_record(
            title=report_title,
            database_name=db_label,
            fmt="HTML",
            analysis_id=bundle.analysis_id,
        )

    if d2.download_button(
        "Download JSON Report",
        data=json_str.encode("utf-8"),
        file_name="querytrellis_report.json",
        mime="application/json",
        width="stretch",
    ):
        store.save_report_record(
            title=report_title,
            database_name=db_label,
            fmt="JSON",
            analysis_id=bundle.analysis_id,
        )

    if bundle.parsed_plan is not None:
        plan_csv = build_plan_nodes_csv(bundle.parsed_plan)
        d3.download_button(
            "Download Plan Nodes CSV",
            data=plan_csv.encode("utf-8"),
            file_name="querytrellis_plan_nodes.csv",
            mime="text/csv",
            width="stretch",
        )
    else:
        d3.button("Plan Nodes CSV (Unavailable)", disabled=True, width="stretch")

    if benchmark is not None and benchmark.success:
        bench_csv = build_benchmark_csv(benchmark)
        d4.download_button(
            "Download Benchmark CSV",
            data=bench_csv.encode("utf-8"),
            file_name="querytrellis_benchmark.csv",
            mime="text/csv",
            width="stretch",
        )
    else:
        d4.button("Benchmark CSV (Run Benchmark First)", disabled=True, width="stretch")

    st.divider()
    tab_prev, tab_hist = st.tabs(["HTML Report Preview", "Export History Log"])
    with tab_prev:
        st.components.v1.html(html_str, height=620, scrolling=True)
    with tab_hist:
        rep_rows = store.list_reports(limit=50)
        if not rep_rows:
            st.info("No report downloads logged in this SQLite store yet.")
        else:
            st.dataframe(pd.DataFrame(rep_rows), width="stretch", hide_index=True)
