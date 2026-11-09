"""SQL Query Editor & Live Schema Browser page for QueryTrellis."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app.components.sql_editor_widget import render_sql_ide
from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_copy_button,
    render_empty_state,
    render_error_state,
    render_section_header,
    render_severity_pill,
    render_telemetry_row,
)
from app.state import navigate_to, set_active_editor_sql
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


def _render_schema_browser(conn_mgr: ConnectionManager) -> None:
    """Render live PostgreSQL schema, columns, indexes, FKs, and template generator."""
    st.markdown(
        "<div style='font-size:0.74rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;"
        "color:var(--qt-text-secondary);margin-bottom:4px;'>Schema &amp; Index Browser</div>",
        unsafe_allow_html=True,
    )

    if not conn_mgr.is_connected:
        render_empty_state(
            "Database Not Connected",
            "Connect to PostgreSQL to inspect tables, columns, data types, existing indexes, and scan ratios.",
            action_label="Open Connection Settings",
            action_key="qt_qe_schema_connect",
            on_action=lambda: (navigate_to("Settings"), st.rerun()),
        )
        return

    c_sel, c_ref = st.columns([3.0, 0.9], vertical_alignment="bottom")
    with c_ref:
        if st.button("Refresh", key="qt_qe_schema_refresh", icon=":material/refresh:", width="stretch"):
            try:
                conn_mgr.fetch_catalog(force_refresh=True)
                st.toast("Catalog metadata refreshed.")
            except Exception as exc:
                st.error(f"Catalog refresh failed: {exc}")

    try:
        catalog = conn_mgr.fetch_catalog()
    except Exception as exc:
        render_error_state("Catalog Error", str(exc))
        return

    if not catalog.tables:
        render_empty_state("No User Tables", "Connected database contains no non-system tables or views.")
        return

    tbl_options = [f"{t.schema_name}.{t.table_name}" for t in catalog.tables]
    with c_sel:
        chosen_tbl = st.selectbox(
            "Target Table / View",
            options=tbl_options,
            key="qt_qe_schema_tbl_sel",
            label_visibility="collapsed",
        )

    sch, tbl_name = chosen_tbl.split(".", 1)
    tmeta = catalog.find_table(tbl_name, schema=sch)
    if not tmeta:
        return

    size_mb = tmeta.total_size_bytes / (1024 * 1024)
    st.markdown(
        f"""
        <div class="qt-surface-card" style="padding:0.48rem 0.65rem;margin-bottom:4px;">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
                <span class="qt-mono" style="font-size:0.78rem;font-weight:600;">{html.escape(chosen_tbl)}</span>
                <span class="qt-pill">{html.escape(tmeta.table_type)}</span>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:4px;font-size:0.73rem;color:var(--qt-text-secondary);font-family:var(--qt-font-mono);">
                <span>Est rows: {tmeta.estimated_rows:,}</span>
                <span>Size: {size_mb:.2f} MB</span>
                <span>Seq/Idx: {tmeta.seq_scan:,}/{tmeta.idx_scan:,}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_cols, tab_idxs, tab_fks = st.tabs(
        [
            f"Columns ({len(tmeta.columns)})",
            f"Indexes ({len(tmeta.indexes)})",
            f"FKs ({len(tmeta.foreign_keys)})",
        ]
    )

    with tab_cols:
        col_df = pd.DataFrame(
            [
                {
                    "Column": c.column_name,
                    "Type": c.data_type,
                    "Null": "YES" if c.is_nullable else "NO",
                }
                for c in tmeta.columns
            ]
        )
        st.dataframe(col_df, width="stretch", hide_index=True, height=215)

    with tab_idxs:
        if not tmeta.indexes:
            st.caption("No indexes defined on this object.")
        else:
            idx_df = pd.DataFrame(
                [
                    {
                        "Index": idx.index_name,
                        "Type": idx.access_method,
                        "Keys": ", ".join(idx.key_columns),
                        "Scans": idx.idx_scan,
                    }
                    for idx in tmeta.indexes
                ]
            )
            st.dataframe(idx_df, width="stretch", hide_index=True, height=215)

    with tab_fks:
        if not tmeta.foreign_keys:
            st.caption("No outgoing foreign keys.")
        else:
            fk_df = pd.DataFrame(
                [
                    {
                        "Column(s)": ", ".join(fk.columns),
                        "References": f"{fk.referenced_table}({', '.join(fk.referenced_columns)})",
                    }
                    for fk in tmeta.foreign_keys
                ]
            )
            st.dataframe(fk_df, width="stretch", hide_index=True, height=215)

    if st.button(
        "Insert SELECT Template",
        key="qt_qe_insert_template",
        icon=":material/add:",
        width="stretch",
        help="Insert a column-explicit read-only SELECT preview for this table into the active tab.",
    ):
        cols = [c.column_name for c in tmeta.columns[:10]]
        col_block = ",\n    ".join(cols) if cols else "*"
        qual_name = tmeta.table_name if tmeta.schema_name == "public" else f"{tmeta.schema_name}.{tmeta.table_name}"
        template = f"SELECT\n    {col_block}\nFROM {qual_name}\nLIMIT 50;"
        set_active_editor_sql(template)
        st.session_state["qt_editor_feedback"] = ("info", f"Inserted SELECT template for {chosen_tbl}.")
        st.rerun()


def render_query_editor_page() -> None:
    """Render SQL Query Editor workspace with tabs, IDE editor, schema explorer, and diagnostics dock."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    timeout_ms = int(st.session_state.get("qt_timeout_ms", 5000))
    max_rows = int(st.session_state.get("qt_max_rows", 500))

    def _send_to_benchmark() -> None:
        curr = st.session_state.get("qt_editor_sql", "")
        st.session_state["qt_pending_single_bench_sql"] = curr
        navigate_to("Benchmark Lab")
        st.rerun()

    render_topbar(
        "Query Editor",
        right_meta=f"READ-ONLY · {timeout_ms}ms · max {max_rows}",
        action_label="Benchmark Query",
        action_icon="speed",
        on_action=_send_to_benchmark,
    )

    # ------------------------------------------------------------------
    # Multi-Tab Workspace Strip
    # ------------------------------------------------------------------
    tabs: list[dict[str, str]] = st.session_state["qt_sql_tabs"]
    active_idx = min(int(st.session_state.get("qt_active_sql_tab", 0)), len(tabs) - 1)
    st.session_state["qt_active_sql_tab"] = active_idx

    tab_cols = st.columns([*(1.0 for _ in tabs), 0.65, 0.72])
    for idx, tab in enumerate(tabs):
        is_curr = idx == active_idx
        if tab_cols[idx].button(
            tab["name"],
            key=f"qt_qe_tab_btn_{idx}",
            type="primary" if is_curr else "secondary",
            width="stretch",
        ):
            if not is_curr:
                tabs[active_idx]["sql"] = st.session_state.get("qt_editor_sql", "")
                st.session_state["qt_active_sql_tab"] = idx
                set_active_editor_sql(tabs[idx]["sql"])
                st.session_state.pop("qt_editor_feedback", None)
                st.rerun()

    if tab_cols[-2].button(
        "+ Tab",
        key="qt_qe_add_tab",
        width="stretch",
        disabled=len(tabs) >= 6,
        help="Open a new SQL scratch tab (up to 6 tabs).",
    ):
        tabs[active_idx]["sql"] = st.session_state.get("qt_editor_sql", "")
        new_num = len(tabs) + 1
        tabs.append({"name": f"Query {new_num}", "sql": "SELECT\n    1 AS health_check;"})
        st.session_state["qt_active_sql_tab"] = len(tabs) - 1
        set_active_editor_sql(tabs[-1]["sql"])
        st.rerun()

    if tab_cols[-1].button(
        "Close",
        key="qt_qe_close_tab",
        width="stretch",
        disabled=len(tabs) <= 1,
        help="Close current SQL tab.",
    ):
        tabs.pop(active_idx)
        next_idx = max(0, active_idx - 1)
        st.session_state["qt_active_sql_tab"] = next_idx
        set_active_editor_sql(tabs[next_idx]["sql"])
        st.rerun()

    # ------------------------------------------------------------------
    # Sample Query Library Strip
    # ------------------------------------------------------------------
    sample_titles = [s.title for s in SAMPLE_QUERIES]
    col_sel, col_load, col_opt = st.columns([2.55, 0.9, 1.15], vertical_alignment="bottom")
    with col_sel:
        selected_title = st.selectbox(
            "Sample Query Library",
            options=sample_titles,
            index=0,
            key="qt_sample_picker",
        )
    chosen_sample = next(s for s in SAMPLE_QUERIES if s.title == selected_title)

    with col_load:
        if st.button("Load Example", key="qt_qe_load_example", width="stretch"):
            set_active_editor_sql(chosen_sample.sql)
            st.session_state["qt_editor_feedback"] = ("info", f"Loaded sample: {chosen_sample.title}")
            st.rerun()

    with col_opt:
        has_opt = chosen_sample.suggested_optimization is not None
        if st.button(
            "Load Optimization Pair",
            key="qt_qe_load_pair",
            width="stretch",
            disabled=not has_opt,
            help="Load the paired optimized SQL rewrite into the active tab and stage both A/B versions for Benchmark Lab.",
        ):
            if chosen_sample.suggested_optimization:
                set_active_editor_sql(chosen_sample.suggested_optimization)
                st.session_state["qt_pending_bench_a"] = chosen_sample.sql
                st.session_state["qt_pending_bench_b"] = chosen_sample.suggested_optimization
                st.session_state["qt_bench_sql_a"] = chosen_sample.sql
                st.session_state["qt_bench_sql_b"] = chosen_sample.suggested_optimization
                st.session_state["qt_editor_feedback"] = (
                    "info",
                    f"Loaded optimized rewrite for '{chosen_sample.title}' (Baseline & Candidate staged for Benchmark Lab).",
                )
                st.rerun()

    st.caption(f"{chosen_sample.category}: {chosen_sample.description}")

    # ------------------------------------------------------------------
    # Main Split Workspace: Left IDE Editor | Right Schema Browser
    # ------------------------------------------------------------------
    col_editor, col_schema = st.columns([1.68, 1.0], gap="medium")

    with col_editor:
        sql_text, triggered_action = render_sql_ide(
            key="qt_sql_ide_instance",
            height=285,
            policy_label=f"READ-ONLY · {timeout_ms} ms · {max_rows} rows",
        )

        # Compact auxiliary bar right under IDE
        s1, s2, s3 = st.columns([1.15, 1.05, 1.05], vertical_alignment="center")
        explain_mode = s1.selectbox(
            "Default Analyze Mode",
            options=["EXPLAIN (ANALYZE, BUFFERS)", "EXPLAIN (Estimate Only)"],
            index=0 if st.session_state.get("qt_explain_analyze", True) else 1,
            key="qt_qe_explain_mode",
            label_visibility="collapsed",
        )
        bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")
        if s2.button("Save Baseline (A)", key="qt_qe_save_a", width="stretch"):
            plan_a = bundle.parsed_plan if (bundle and bundle.sql_text == sql_text) else None
            ap_a = bundle.antipatterns if (bundle and bundle.sql_text == sql_text) else []
            st.session_state["qt_baseline_snapshot"] = QuerySnapshot(
                label="Baseline (A)",
                sql_text=sql_text,
                plan=plan_a,
                antipatterns=ap_a,
            )
            st.session_state["qt_bench_sql_a"] = sql_text
            st.session_state["qt_pending_bench_a"] = sql_text
            st.session_state["qt_editor_feedback"] = ("ok", "Saved active SQL as Comparison Baseline (A) for Benchmark Lab.")
        if s3.button("Save Candidate (B)", key="qt_qe_save_b", width="stretch"):
            plan_b = bundle.parsed_plan if (bundle and bundle.sql_text == sql_text) else None
            ap_b = bundle.antipatterns if (bundle and bundle.sql_text == sql_text) else []
            st.session_state["qt_candidate_snapshot"] = QuerySnapshot(
                label="Optimized (B)",
                sql_text=sql_text,
                plan=plan_b,
                antipatterns=ap_b,
            )
            st.session_state["qt_bench_sql_b"] = sql_text
            st.session_state["qt_pending_bench_b"] = sql_text
            st.session_state["qt_editor_feedback"] = ("ok", "Saved active SQL as Comparison Candidate (B) for Benchmark Lab.")

        # Dispatch IDE toolbar / shortcut triggers
        if triggered_action == "clear":
            set_active_editor_sql("")
            st.session_state["qt_last_exec"] = None
            st.session_state["qt_editor_feedback"] = ("info", "Cleared active SQL editor tab.")
            st.rerun()

        elif triggered_action == "format":
            formatted, fmt_err = format_sql(sql_text)
            if fmt_err:
                st.session_state["qt_editor_feedback"] = ("err", fmt_err)
            else:
                set_active_editor_sql(formatted)
                st.session_state["qt_editor_feedback"] = ("ok", "Formatted SQL cleanly.")
                st.rerun()

        elif triggered_action == "validate":
            val = validate_read_only_sql(sql_text)
            if val.is_valid and val.is_read_only:
                info = val.parsed_info
                tables_str = ", ".join(t.table for t in info.tables) if info and info.tables else "None"
                st.session_state["qt_editor_feedback"] = (
                    "ok",
                    f"Validation passed ({info.statement_type if info else 'SELECT'}). Referenced tables: {tables_str}.",
                )
            else:
                st.session_state["qt_editor_feedback"] = ("err", f"Validation rejected: {val.error_message}")

        elif triggered_action == "execute":
            if not conn_mgr.is_connected:
                st.session_state["qt_editor_feedback"] = (
                    "err",
                    "PostgreSQL is not connected. Open Settings to connect before executing queries.",
                )
            else:
                with st.spinner("Executing validated read-only SELECT..."):
                    res = execute_and_record_query(
                        sql_text,
                        conn_manager=conn_mgr,
                        metadata_store=store,
                        timeout_ms=timeout_ms,
                        max_rows=max_rows,
                        persist=True,
                    )
                st.session_state["qt_last_exec"] = res
                if res.success:
                    st.session_state["qt_editor_feedback"] = (
                        "ok",
                        f"Executed read-only SELECT in {res.client_duration_ms:.2f} ms ({res.rows_returned:,} row(s) returned).",
                    )
                else:
                    st.session_state["qt_editor_feedback"] = ("err", res.error_message)

        elif triggered_action in ("analyze", "explain"):
            use_analyze = triggered_action == "analyze" and explain_mode.startswith("EXPLAIN (ANALYZE")
            with st.spinner("Running AST analysis, anti-pattern rules, EXPLAIN, and index advisor..."):
                new_bundle = analyze_query_end_to_end(
                    sql_text,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=use_analyze,
                    buffers=use_analyze,
                    timeout_ms=timeout_ms,
                    persist=True,
                )
            st.session_state["qt_last_analysis"] = new_bundle
            st.session_state["qt_selected_plan_node_id"] = 0
            if not new_bundle.validation.is_valid or not new_bundle.validation.is_read_only:
                st.session_state["qt_editor_feedback"] = ("err", f"Analysis rejected: {new_bundle.error_message}")
            elif new_bundle.error_message:
                st.session_state["qt_editor_feedback"] = ("warn", new_bundle.error_message)
            elif not conn_mgr.is_connected:
                st.session_state["qt_editor_feedback"] = (
                    "info",
                    f"Static AST analysis complete ({len(new_bundle.antipatterns)} anti-pattern(s), "
                    f"{len(new_bundle.index_recommendations)} index hint(s)). Connect PG for EXPLAIN plans.",
                )
            else:
                p = new_bundle.parsed_plan
                pg_t = f"PG Exec {p.execution_time_ms:.3f} ms · " if (p and p.execution_time_ms is not None) else ""
                st.session_state["qt_editor_feedback"] = (
                    "ok",
                    f"Analysis complete: {pg_t}{len(new_bundle.antipatterns)} anti-pattern(s), "
                    f"{len(new_bundle.index_recommendations)} index suggestion(s).",
                )

        fb = st.session_state.get("qt_editor_feedback")
        if fb:
            lvl, msg = fb
            bcls = {
                "ok": "qt-banner",
                "info": "qt-banner",
                "warn": "qt-banner qt-banner-warn",
                "err": "qt-banner qt-banner-err",
            }.get(lvl, "qt-banner")
            st.markdown(f"<div class='{bcls}'>{html.escape(msg)}</div>", unsafe_allow_html=True)

    with col_schema:
        _render_schema_browser(conn_mgr)

    # ------------------------------------------------------------------
    # Bottom Tabbed Results & Diagnostics Dock
    # ------------------------------------------------------------------
    exec_res = st.session_state.get("qt_last_exec")
    bundle = st.session_state.get("qt_last_analysis")
    plan = bundle.parsed_plan if bundle else None
    ap_list = bundle.antipatterns if bundle else []
    idx_list = bundle.index_recommendations if bundle else []

    render_section_header(
        "Execution Results & Diagnostics Dock",
        f"Latest Analysis #{bundle.analysis_id}" if (bundle and bundle.analysis_id) else "Session Diagnostics",
    )

    tab_res, tab_plan, tab_ap, tab_idx, tab_msg = st.tabs(
        [
            f"Query Results ({exec_res.rows_returned:,})" if (exec_res and exec_res.success) else "Query Results",
            f"Plan Summary ({len(plan.all_nodes)} nodes)" if plan else "Plan Summary",
            f"Anti-Patterns ({len(ap_list)})",
            f"Index Hints ({len(idx_list)})",
            "Messages & Guardrails",
        ]
    )

    with tab_res:
        if exec_res is None:
            render_empty_state(
                "No Query Executed Yet",
                "Click Execute (Ctrl+Enter) in the SQL editor toolbar to view paginated result rows.",
            )
        elif not exec_res.success:
            render_error_state("Execution Blocked / Failed", exec_res.error_message)
        else:
            render_telemetry_row(
                [
                    TelemetryCardData(label="Status", value="Success", subtext="Read-only transaction", accent=True, tone="ok"),
                    TelemetryCardData(label="Client Duration", value=f"{exec_res.client_duration_ms:.3f} ms", subtext="Includes driver IPC"),
                    TelemetryCardData(
                        label="Rows Returned",
                        value=f"{exec_res.rows_returned:,}",
                        subtext=f"Capped at {exec_res.max_rows_applied}" if exec_res.was_truncated else "Complete result set",
                        tone="warn" if exec_res.was_truncated else "ok",
                    ),
                    TelemetryCardData(label="Columns", value=f"{len(exec_res.columns)}", subtext=", ".join(exec_res.columns[:4])),
                    TelemetryCardData(label="Max Row Policy", value=f"{exec_res.max_rows_applied:,}", subtext="Configured in Settings"),
                ]
            )
            if exec_res.was_truncated:
                st.markdown(
                    f"<div class='qt-banner qt-banner-warn'>Output truncated to {exec_res.max_rows_applied} rows to keep the workbench responsive.</div>",
                    unsafe_allow_html=True,
                )
            if exec_res.rows:
                df = pd.DataFrame(exec_res.rows, columns=exec_res.columns)
                st.dataframe(df, width="stretch", hide_index=True, height=290)
                st.download_button(
                    "Download Results CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="querytrellis_results.csv",
                    mime="text/csv",
                    key="qt_qe_dl_csv",
                )
            else:
                st.markdown("<div class='qt-banner'>Query succeeded and returned 0 rows.</div>", unsafe_allow_html=True)

    with tab_plan:
        if bundle is None:
            render_empty_state("No Plan Captured", "Click Explain Analyze (Shift+Enter) or Explain in the toolbar.")
        elif plan is None:
            render_empty_state(
                "Execution Plan Unavailable",
                bundle.error_message or "Connect to PostgreSQL to inspect EXPLAIN / EXPLAIN ANALYZE execution plans.",
            )
        else:
            render_telemetry_row(
                [
                    TelemetryCardData(
                        label="PG Execution Time",
                        value=f"{plan.execution_time_ms:.3f} ms" if plan.execution_time_ms is not None else "Unavailable",
                        subtext="Server-side" if plan.analyzed else "Estimate only",
                        accent=True,
                        tone="ok" if plan.analyzed else "neutral",
                    ),
                    TelemetryCardData(
                        label="PG Planning Time",
                        value=f"{plan.planning_time_ms:.3f} ms" if plan.planning_time_ms is not None else "Unavailable",
                        subtext="Optimizer latency",
                    ),
                    TelemetryCardData(
                        label="Total Est Cost",
                        value=f"{plan.total_cost:,.2f}" if plan.total_cost is not None else "Unavailable",
                        subtext=f"{len(plan.all_nodes)} plan node(s)",
                    ),
                    TelemetryCardData(
                        label="Root Rows (Act/Est)",
                        value=f"{plan.root_actual_rows:,}" if plan.root_actual_rows is not None else f"Est {plan.root_plan_rows or 0:,}",
                        subtext=f"Indexes: {', '.join(plan.used_indexes) or 'None'}",
                    ),
                    TelemetryCardData(
                        label="Plan Bottlenecks",
                        value=f"{len(bundle.plan_insights)}",
                        subtext="From plan analyzer",
                    ),
                ]
            )
            st.code(plan.to_text_tree(), language="text")
            if st.button("Inspect Interactive Plan Tree", key="qt_qe_goto_plan", type="primary", icon=":material/account_tree:"):
                navigate_to("Explain Plan")
                st.rerun()

    with tab_ap:
        if not ap_list:
            render_empty_state(
                "No SQL Anti-Patterns Flagged",
                "Run Explain Analyze / Explain on a statement to evaluate all 15 PostgreSQL anti-pattern rules.",
            )
        else:
            for f in ap_list:
                sev_badge = render_severity_pill(f.severity)
                st.markdown(
                    f"<div class='qt-surface-card' style='margin-bottom:6px;'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;'>"
                    f"<span style='font-weight:600;font-size:0.86rem;'>{html.escape(f.rule_id)} &middot; {html.escape(f.issue_name)}</span>"
                    f"<span>{sev_badge} <span class='qt-pill'>{html.escape(f.evidence_basis)}</span></span>"
                    f"</div>"
                    f"<div class='qt-mono' style='font-size:0.76rem;color:var(--qt-accent-text);margin-top:4px;'>{html.escape(f.affected_fragment)}</div>"
                    f"<div style='font-size:0.79rem;color:var(--qt-text-secondary);margin-top:4px;'>{html.escape(f.explanation)}</div>"
                    f"<div style='font-size:0.78rem;color:var(--qt-text-primary);margin-top:4px;'><strong>Suggested:</strong> {html.escape(f.suggested_improvement)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            if st.button("Open Recommendations Workspace", key="qt_qe_goto_recs", icon=":material/lightbulb:"):
                navigate_to("Recommendations")
                st.rerun()

    with tab_idx:
        if not idx_list:
            render_empty_state(
                "No Additional Index Suggestions",
                "Existing indexes cover detected predicates or predicates require rewrite before indexing helps.",
            )
        else:
            st.markdown(
                "<div class='qt-banner' style='margin-bottom:6px;'>"
                "<strong>Advisory Only:</strong> QueryTrellis never applies DDL automatically. Test write overhead before creating indexes."
                "</div>",
                unsafe_allow_html=True,
            )
            for idx_num, r in enumerate(idx_list):
                with st.container():
                    c_info, c_copy = st.columns([2.6, 1.0], vertical_alignment="center")
                    c_info.markdown(
                        f"**{r.rec_id}** &mdash; `{r.index_type}` on `{r.table_name}({', '.join(r.columns)})` "
                        f"(`{r.confidence}` confidence)"
                    )
                    with c_copy:
                        render_copy_button(r.suggested_sql, key=f"qt_qe_idx_copy_{idx_num}")
                    st.code(r.suggested_sql, language="sql")
                    st.caption(f"Condition: {r.related_condition} | {r.why_it_helps}")

    with tab_msg:
        st.markdown(
            f"""
            <div class="qt-surface-card">
                <div style="font-weight:600;font-size:0.84rem;margin-bottom:4px;">Active Safe Execution Policy</div>
                <ul style="margin:0;padding-left:1.2rem;font-size:0.79rem;color:var(--qt-text-secondary);line-height:1.5;">
                    <li>Single read-only <code>SELECT</code> / CTE statements enforced via SQLGlot AST inspection.</li>
                    <li>Write/admin commands (<code>INSERT</code>, <code>UPDATE</code>, <code>DELETE</code>, <code>DROP</code>, <code>ALTER</code>, <code>CREATE</code>, <code>GRANT</code>) rejected prior to execution.</li>
                    <li>Every live execution wraps inside <code>SET TRANSACTION READ ONLY</code> with <code>SET LOCAL statement_timeout = '{timeout_ms}ms'</code>.</li>
                    <li>Preview results capped at <strong>{max_rows} rows</strong>; <code>EXPLAIN ANALYZE</code> runs inside a read-only rolled-back transaction.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if bundle and bundle.error_message:
            render_error_state("Last Analysis Message", bundle.error_message)
        if exec_res and not exec_res.success:
            render_error_state("Last Execution Error", exec_res.error_message)
