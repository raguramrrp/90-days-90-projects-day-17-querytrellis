"""B. SQL Query Editor page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.sidebar import render_page_header
from app.components.sql_editor_widget import render_sql_editor_box
from src.benchmark.comparator import QuerySnapshot
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.services.workbench_service import (
    FullAnalysisBundle,
    analyze_query_end_to_end,
    execute_and_record_query,
)
from src.sql_analysis.formatter import format_sql
from src.sql_analysis.parser_validator import validate_read_only_sql
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def render_query_editor_page() -> None:
    render_page_header(
        "SQL Query Editor",
        "Write, validate, format, safely execute, and analyze PostgreSQL SELECT queries.",
    )

    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]

    # Example query selector row
    sample_titles = [s.title for s in SAMPLE_QUERIES]
    col_sel, col_load, col_opt = st.columns([2.6, 0.9, 1.1])
    with col_sel:
        selected_title = st.selectbox(
            "Sample Query Library",
            options=sample_titles,
            index=0,
            key="qt_sample_picker",
        )
    chosen_sample = next(s for s in SAMPLE_QUERIES if s.title == selected_title)

    with col_load:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Load Example", width="stretch"):
            st.session_state["qt_pending_editor_sql"] = chosen_sample.sql
            st.rerun()

    with col_opt:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        has_opt = chosen_sample.suggested_optimization is not None
        if st.button(
            "Load Optimization Pair",
            width="stretch",
            disabled=not has_opt,
            help="Loads the paired optimized SQL rewrite into the editor (when available).",
        ):
            if chosen_sample.suggested_optimization:
                st.session_state["qt_pending_editor_sql"] = chosen_sample.suggested_optimization
                st.rerun()

    st.caption(f"{chosen_sample.category}: {chosen_sample.description}")

    # SQL Editor input
    sql_text = render_sql_editor_box(height=230, show_highlight_preview=True)

    # Action controls + EXPLAIN option
    c_val, c_fmt, c_exec, c_ana, c_clr, c_mode = st.columns([0.9, 0.9, 1.0, 1.05, 0.75, 1.6])
    btn_validate = c_val.button("Validate", width="stretch")
    btn_format = c_fmt.button("Format SQL", width="stretch")
    btn_execute = c_exec.button("Execute", type="primary", width="stretch")
    btn_analyze = c_ana.button("Analyze Query", type="primary", width="stretch")
    btn_clear = c_clr.button("Clear", width="stretch")
    explain_mode = c_mode.selectbox(
        "Explain Mode",
        options=["EXPLAIN (ANALYZE, BUFFERS)", "EXPLAIN (Estimate Only)"],
        index=0 if st.session_state.get("qt_explain_analyze", True) else 1,
        label_visibility="collapsed",
    )
    use_analyze = explain_mode.startswith("EXPLAIN (ANALYZE")

    st.markdown(
        "<div class='qt-caveat'>"
        "<strong>Execution Safety:</strong> Only single read-only SELECT statements are permitted. "
        "Queries run inside <code>SET TRANSACTION READ ONLY</code> with a "
        f"<code>{st.session_state['qt_timeout_ms']} ms</code> statement timeout and "
        f"<code>{st.session_state['qt_max_rows']}</code> row cap. "
        "<strong>Note:</strong> <code>EXPLAIN ANALYZE</code> executes the validated read-only query "
        "on PostgreSQL inside the read-only transaction to measure actual row counts, timings, and buffers."
        "</div>",
        unsafe_allow_html=True,
    )

    if btn_clear:
        st.session_state["qt_pending_editor_sql"] = ""
        st.session_state["qt_last_exec"] = None
        st.rerun()

    if btn_format:
        formatted, fmt_err = format_sql(sql_text)
        if fmt_err:
            st.warning(fmt_err)
        else:
            st.session_state["qt_pending_editor_sql"] = formatted
            st.rerun()

    if btn_validate:
        val = validate_read_only_sql(sql_text)
        if val.is_valid and val.is_read_only:
            info = val.parsed_info
            tables_str = ", ".join(t.table for t in info.tables) if info and info.tables else "None"
            st.success(
                f"Validation passed ({info.statement_type if info else 'SELECT'}). "
                f"Referenced tables: {tables_str}."
            )
        else:
            st.error(f"Validation rejected: {val.error_message}")

    if btn_execute:
        if not conn_mgr.is_connected:
            st.error("PostgreSQL is not connected. Connect to a database in Settings first.")
        else:
            with st.spinner("Executing validated read-only query..."):
                res = execute_and_record_query(
                    sql_text,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                    max_rows=st.session_state["qt_max_rows"],
                    persist=True,
                )
            st.session_state["qt_last_exec"] = res

    if btn_analyze:
        with st.spinner("Running AST analysis, anti-pattern rules, EXPLAIN, and index advisor..."):
            bundle = analyze_query_end_to_end(
                sql_text,
                conn_manager=conn_mgr,
                metadata_store=store,
                analyze_explain=use_analyze,
                buffers=use_analyze,
                timeout_ms=st.session_state["qt_timeout_ms"],
                persist=True,
            )
        st.session_state["qt_last_analysis"] = bundle

    # Display Execute Query Results
    exec_res = st.session_state.get("qt_last_exec")
    if exec_res is not None:
        st.divider()
        st.subheader("Query Execution Output")
        if not exec_res.success:
            st.error(f"Execution blocked/failed: {exec_res.error_message}")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Status", "Success (Read-Only)")
            m2.metric("Client Duration", f"{exec_res.client_duration_ms:.3f} ms")
            m3.metric("Rows Returned", f"{exec_res.rows_returned:,}" + (" (Truncated)" if exec_res.was_truncated else ""))
            if exec_res.was_truncated:
                st.warning(
                    f"Output truncated to {exec_res.max_rows_applied} rows to protect UI responsiveness. "
                    "Adjust Max Rows in Settings if needed."
                )
            if exec_res.rows:
                df = pd.DataFrame(exec_res.rows, columns=exec_res.columns)
                st.dataframe(df, width="stretch", hide_index=True)
                st.download_button(
                    "Download Results CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="querytrellis_results.csv",
                    mime="text/csv",
                )
            else:
                st.info("Query succeeded and returned 0 rows.")

    # Display Latest Analysis Summary Strip
    bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")
    if bundle is not None:
        st.divider()
        st.subheader("Latest Analysis Summary")
        if not bundle.validation.is_valid or not bundle.validation.is_read_only:
            st.error(f"Analysis rejected: {bundle.error_message}")
        else:
            if bundle.error_message:
                st.warning(bundle.error_message)
            elif not conn_mgr.is_connected:
                st.info(
                    "Static AST anti-pattern & structural index analysis completed offline. "
                    "Connect PostgreSQL to include live EXPLAIN (ANALYZE, BUFFERS) plans."
                )

            plan = bundle.parsed_plan
            a1, a2, a3, a4 = st.columns(4)
            a1.metric(
                "PG Execution Time",
                f"{plan.execution_time_ms:.3f} ms" if (plan and plan.execution_time_ms is not None) else "Unavailable",
            )
            a2.metric(
                "Plan Total Cost",
                f"{plan.total_cost:,.2f}" if (plan and plan.total_cost is not None) else "Unavailable",
            )
            a3.metric("Anti-Patterns Flagged", f"{len(bundle.antipatterns)}")
            a4.metric("Index Suggestions", f"{len(bundle.index_recommendations)}")

            b1, b2, b3, b4 = st.columns(4)
            if b1.button("Open Explain Plan", width="stretch"):
                st.session_state["qt_nav_page"] = "Explain Plan"
                st.rerun()
            if b2.button("Open Recommendations", width="stretch"):
                st.session_state["qt_nav_page"] = "Recommendations"
                st.rerun()
            if b3.button("Save as Comparison Baseline (A)", width="stretch"):
                st.session_state["qt_baseline_snapshot"] = QuerySnapshot(
                    label="Baseline (A)",
                    sql_text=bundle.sql_text,
                    plan=bundle.parsed_plan,
                    antipatterns=bundle.antipatterns,
                )
                st.session_state["qt_bench_sql_a"] = bundle.sql_text
                st.success("Saved current analysis as Comparison Baseline (A).")
            if b4.button("Save as Candidate (B)", width="stretch"):
                st.session_state["qt_candidate_snapshot"] = QuerySnapshot(
                    label="Optimized (B)",
                    sql_text=bundle.sql_text,
                    plan=bundle.parsed_plan,
                    antipatterns=bundle.antipatterns,
                )
                st.session_state["qt_bench_sql_b"] = bundle.sql_text
                st.success("Saved current analysis as Comparison Candidate (B).")
