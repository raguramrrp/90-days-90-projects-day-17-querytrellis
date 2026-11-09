"""Settings, Database Connection Manager, Appearance & Storage page for QueryTrellis."""
from __future__ import annotations

import html
import sqlite3

import streamlit as st

from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_empty_state,
    render_error_state,
    render_section_header,
    render_telemetry_row,
)
from app.theme import DARK_THEME, LIGHT_THEME, get_active_theme, set_active_theme
from src.config.settings import ConnectionConfig
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore


@st.dialog("Confirm Profile Deletion")
def _confirm_delete_profile_dialog(store: MetadataStore, profile_name: str) -> None:
    st.markdown(
        f"Delete saved PostgreSQL connection profile **`{profile_name}`** from local SQLite storage? "
        "This only removes connection metadata; your PostgreSQL database is untouched."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch", key="qt_dlg_prof_cancel"):
        st.rerun()
    if c2.button("Delete Profile", type="primary", width="stretch", key="qt_dlg_prof_confirm"):
        store.delete_connection_profile(profile_name)
        st.toast(f"Deleted profile '{profile_name}'.")
        st.rerun()


@st.dialog("Confirm Local History Cleanup")
def _confirm_clear_history_dialog(store: MetadataStore) -> None:
    st.markdown(
        "Remove all recorded **query analyses, benchmark runs, before/after comparisons, and report logs** "
        "from local SQLite storage? Saved connection profiles and UI preferences will be preserved."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch", key="qt_dlg_hist_cancel"):
        st.rerun()
    if c2.button("Clear Recorded History", type="primary", width="stretch", key="qt_dlg_hist_confirm"):
        db_target = str(store.db_path)
        if db_target != ":memory:":
            conn = sqlite3.connect(db_target)
            try:
                with conn:
                    conn.execute("DELETE FROM report_history")
                    conn.execute("DELETE FROM query_comparisons")
                    conn.execute("DELETE FROM benchmark_runs")
                    conn.execute("DELETE FROM query_analyses")
            finally:
                conn.close()
        st.session_state["qt_last_analysis"] = None
        st.session_state["qt_last_benchmark"] = None
        st.session_state["qt_last_comparison"] = None
        st.session_state["qt_baseline_snapshot"] = None
        st.session_state["qt_candidate_snapshot"] = None
        st.toast("Cleared recorded workbench history.")
        st.rerun()


def render_settings_page() -> None:
    """Render Connection Manager, Safety Guardrails, Theme Appearance, and Local Storage settings."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    curr_cfg = conn_mgr.config
    status = conn_mgr.status
    theme = get_active_theme()

    render_topbar(
        "Settings",
        right_meta=f"Theme: {'Dark Graphite' if theme.is_dark else 'Crisp Light'}",
        show_disconnected_banner=False,
    )

    tab_conn, tab_safety, tab_appear, tab_storage = st.tabs(
        [
            "Database Connection",
            "Execution Safety",
            "Appearance",
            "Application & Storage",
        ]
    )

    # ------------------------------------------------------------------
    # Section 1: Database Connection & Profiles
    # ------------------------------------------------------------------
    with tab_conn:
        profiles = store.list_connection_profiles()
        if profiles:
            render_section_header("Saved Connection Profiles", "Credentials/passwords are never persisted to SQLite")
            prof_names = ["-- Current / Manual --"] + [p["name"] for p in profiles]
            p_col1, p_col2, p_col3 = st.columns([2.2, 0.9, 0.9], vertical_alignment="bottom")
            chosen_prof = p_col1.selectbox(
                "Saved Connection Profile",
                options=prof_names,
                key="qt_set_prof_sel",
            )
            if chosen_prof != "-- Current / Manual --":
                prof_data = next(p for p in profiles if p["name"] == chosen_prof)
                if p_col2.button("Load Profile", key="qt_set_load_prof", width="stretch"):
                    st.session_state["qt_cfg_host"] = prof_data["host"]
                    st.session_state["qt_cfg_port"] = int(prof_data["port"])
                    st.session_state["qt_cfg_db"] = prof_data["database_name"]
                    st.session_state["qt_cfg_user"] = prof_data["username"]
                    st.session_state["qt_cfg_ssl"] = prof_data["sslmode"]
                    st.toast(f"Loaded connection profile '{chosen_prof}'.")
                    st.rerun()
                if p_col3.button("Delete Profile", key="qt_set_del_prof", width="stretch"):
                    _confirm_delete_profile_dialog(store, chosen_prof)

        render_section_header("PostgreSQL Server Configuration", "Passwords exist in memory only for the active session")
        st.session_state.setdefault("qt_cfg_host", curr_cfg.host)
        st.session_state.setdefault("qt_cfg_port", int(curr_cfg.port))
        st.session_state.setdefault("qt_cfg_db", curr_cfg.database)
        st.session_state.setdefault("qt_cfg_user", curr_cfg.username)
        st.session_state.setdefault(
            "qt_cfg_ssl",
            curr_cfg.sslmode if curr_cfg.sslmode in ("prefer", "disable", "allow", "require") else "prefer",
        )

        c1, c2, c3 = st.columns([1.8, 0.8, 1.4])
        host = c1.text_input("Host", key="qt_cfg_host")
        port = c2.number_input("Port", min_value=1, max_value=65535, key="qt_cfg_port")
        database = c3.text_input("Database Name", key="qt_cfg_db")

        c4, c5, c6 = st.columns([1.3, 1.45, 1.1])
        username = c4.text_input("Username", key="qt_cfg_user")
        # Security Fix: never pre-populate existing password back into widget DOM value=
        pwd_placeholder = (
            "In-memory session password set (leave blank to keep)"
            if curr_cfg.password
            else "Enter password (or leave blank for trust/env)"
        )
        password_input = c5.text_input(
            "Password (Session Memory Only)",
            value="",
            type="password",
            placeholder=pwd_placeholder,
            key="qt_cfg_pwd_input",
        )
        sslmode = c6.selectbox(
            "SSL Mode",
            options=["prefer", "disable", "allow", "require"],
            key="qt_cfg_ssl",
        )

        clear_pwd = False
        if curr_cfg.password:
            cp1, cp2 = st.columns([1.6, 2.0], vertical_alignment="center")
            cp1.markdown(
                "<span class='qt-pill qt-pill-ok'>Session password cached in Python memory (not exposed to DOM)</span>",
                unsafe_allow_html=True,
            )
            clear_pwd = cp2.checkbox("Use empty password instead of cached session password", key="qt_cfg_clear_pwd")

        effective_password = "" if clear_pwd else (password_input if password_input else curr_cfg.password)

        new_cfg = ConnectionConfig(
            host=host.strip() or "localhost",
            port=int(port),
            database=database.strip() or "postgres",
            username=username.strip() or "postgres",
            password=effective_password,
            sslmode=sslmode,
            connect_timeout=curr_cfg.connect_timeout,
        )

        b1, b2, b3 = st.columns(3)
        if b1.button("Test Connection", key="qt_set_test_conn", width="stretch"):
            res = ConnectionManager.test_connection(new_cfg)
            if res.connected:
                st.success(f"Connection succeeded: {res.server_version.split(',')[0]} | Database: {res.current_database}")
            else:
                render_error_state("Connection Test Failed", res.error_message)

        if b2.button("Connect PostgreSQL", key="qt_set_connect", type="primary", width="stretch"):
            res = conn_mgr.connect(new_cfg)
            if res.connected:
                try:
                    conn_mgr.fetch_catalog(force_refresh=True)
                except Exception:
                    pass
                st.toast(f"Connected to {res.current_database} on {res.config.host}:{res.config.port}.")
                st.rerun()
            else:
                render_error_state("Connection Failed", res.error_message)

        if b3.button("Disconnect", key="qt_set_disc", width="stretch", disabled=not status.connected):
            conn_mgr.disconnect()
            st.toast("Disconnected from PostgreSQL.")
            st.rerun()

        render_section_header("Save Current Endpoint as Reusable Profile")
        sp1, sp2 = st.columns([2.2, 1.0], vertical_alignment="bottom")
        prof_name = sp1.text_input("Profile Name", value="Local Sample DB", key="qt_set_prof_name")
        if sp2.button("Save Profile (No Password)", key="qt_set_save_prof", width="stretch"):
            clean_name = prof_name.strip() or "Local PostgreSQL"
            store.save_connection_profile(
                name=clean_name,
                host=new_cfg.host,
                port=new_cfg.port,
                database_name=new_cfg.database,
                username=new_cfg.username,
                sslmode=new_cfg.sslmode,
                is_default=True,
            )
            st.success(f"Saved connection profile '{clean_name}' cleanly (password excluded).")

        if status.connected:
            render_section_header("Active Session & Database Switcher", status.current_database)
            esc = html.escape
            st.markdown(
                f"""
                <div class="qt-surface-card" style="margin-bottom:8px;">
                    <div style="font-size:0.80rem;"><strong>Server Version:</strong> <code class="qt-mono">{esc(status.server_version)}</code></div>
                    <div style="font-size:0.80rem;margin-top:4px;"><strong>Current Database:</strong> <code class="qt-mono">{esc(status.current_database)}</code> &bull;
                    <strong>Role:</strong> <code class="qt-mono">{esc(status.current_user)}</code></div>
                    <div style="font-size:0.80rem;margin-top:4px;"><strong>Available Schemas:</strong> <code class="qt-mono">{esc(', '.join(status.available_schemas) or 'public')}</code></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if status.available_databases:
                sw1, sw2 = st.columns([2.2, 1.0], vertical_alignment="bottom")
                db_sel = sw1.selectbox(
                    "Switch Target Database",
                    options=status.available_databases,
                    index=(
                        status.available_databases.index(status.current_database)
                        if status.current_database in status.available_databases
                        else 0
                    ),
                    key="qt_set_switch_db_sel",
                )
                if sw2.button("Switch Database", key="qt_set_switch_db_btn", width="stretch"):
                    sw = conn_mgr.switch_database(db_sel)
                    if sw.connected:
                        conn_mgr.fetch_catalog(force_refresh=True)
                        st.toast(f"Switched active database to {db_sel}.")
                        st.rerun()
                    else:
                        render_error_state("Database Switch Failed", sw.error_message)

    # ------------------------------------------------------------------
    # Section 2: Execution Safety & Guardrails
    # ------------------------------------------------------------------
    with tab_safety:
        render_section_header("Read-Only Query Guardrails", "Enforced across Query Editor, Explain Plan, and Benchmark Lab")
        st.markdown(
            """
            <div class="qt-banner" style="margin-bottom:8px;">
                <strong>Strict Read-Only Execution Contract:</strong> Every query passes SQLGlot AST parsing before reaching PostgreSQL.
                Write operations (<code>INSERT</code>, <code>UPDATE</code>, <code>DELETE</code>, <code>DDL</code>, <code>GRANT</code>) and multi-statement batches are rejected.
                Permitted statements execute inside explicit <code>SET TRANSACTION READ ONLY</code> blocks with local statement timeouts and client row caps.
            </div>
            """,
            unsafe_allow_html=True,
        )

        s1, s2 = st.columns(2)
        t_ms = s1.number_input(
            "Default Statement Timeout (ms)",
            min_value=100,
            max_value=60000,
            value=int(st.session_state["qt_timeout_ms"]),
            step=500,
            key="qt_set_timeout_ms",
        )
        m_rows = s2.number_input(
            "Default Maximum Returned Rows",
            min_value=10,
            max_value=5000,
            value=int(st.session_state["qt_max_rows"]),
            step=50,
            key="qt_set_max_rows",
        )
        def_analyze = st.checkbox(
            "Default to EXPLAIN (ANALYZE, BUFFERS) when connected",
            value=bool(st.session_state["qt_explain_analyze"]),
            key="qt_set_def_analyze",
        )
        if st.button("Save Safety Preferences", key="qt_set_save_safety", type="primary"):
            st.session_state["qt_timeout_ms"] = int(t_ms)
            st.session_state["qt_max_rows"] = int(m_rows)
            st.session_state["qt_explain_analyze"] = bool(def_analyze)
            store.set_preference("statement_timeout_ms", str(int(t_ms)))
            store.set_preference("max_rows", str(int(m_rows)))
            store.set_preference("explain_analyze_default", "true" if def_analyze else "false")
            st.success("Guardrail preferences saved to local SQLite metadata.")

    # ------------------------------------------------------------------
    # Section 3: Appearance & Theme
    # ------------------------------------------------------------------
    with tab_appear:
        render_section_header("Interface Theme", "Persists locally and updates all surfaces, editors, and charts")
        c_dark, c_light = st.columns(2, gap="medium")

        with c_dark:
            is_d = theme.is_dark
            st.markdown(
                f"""
                <div class="qt-surface-card" style="border-color:{DARK_THEME.accent if is_d else 'var(--qt-border-subtle)'};">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <strong style="font-size:0.90rem;">Dark Graphite (Default)</strong>
                        <span class="qt-pill {'qt-pill-accent' if is_d else ''}">{'Active' if is_d else 'Available'}</span>
                    </div>
                    <div style="font-size:0.78rem;color:var(--qt-text-secondary);margin-top:4px;">
                        Low-glare charcoal workstation surface with restrained teal highlights and crisp monospace legibility.
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <span style="width:24px;height:14px;border-radius:3px;background:{DARK_THEME.bg_app};border:1px solid {DARK_THEME.border};display:inline-block;" title="App BG"></span>
                        <span style="width:24px;height:14px;border-radius:3px;background:{DARK_THEME.bg_surface};border:1px solid {DARK_THEME.border};display:inline-block;" title="Surface"></span>
                        <span style="width:24px;height:14px;border-radius:3px;background:{DARK_THEME.accent};display:inline-block;" title="Accent"></span>
                        <span style="width:24px;height:14px;border-radius:3px;background:{DARK_THEME.text_primary};display:inline-block;" title="Text"></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Apply Dark Graphite",
                key="qt_set_apply_dark",
                type="primary" if not is_d else "secondary",
                disabled=is_d,
                width="stretch",
            ):
                set_active_theme("dark")
                st.rerun()

        with c_light:
            is_l = not theme.is_dark
            st.markdown(
                f"""
                <div class="qt-surface-card" style="border-color:{LIGHT_THEME.accent if is_l else 'var(--qt-border-subtle)'};">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <strong style="font-size:0.90rem;">Crisp Light</strong>
                        <span class="qt-pill {'qt-pill-accent' if is_l else ''}">{'Active' if is_l else 'Available'}</span>
                    </div>
                    <div style="font-size:0.78rem;color:var(--qt-text-secondary);margin-top:4px;">
                        Cool off-white daylight surface with elevated white panels, slate dividers, and high-contrast navy typography.
                    </div>
                    <div style="display:flex;gap:8px;margin-top:8px;">
                        <span style="width:24px;height:14px;border-radius:3px;background:{LIGHT_THEME.bg_app};border:1px solid {LIGHT_THEME.border};display:inline-block;" title="App BG"></span>
                        <span style="width:24px;height:14px;border-radius:3px;background:{LIGHT_THEME.bg_surface};border:1px solid {LIGHT_THEME.border};display:inline-block;" title="Surface"></span>
                        <span style="width:24px;height:14px;border-radius:3px;background:{LIGHT_THEME.accent};display:inline-block;" title="Accent"></span>
                        <span style="width:24px;height:14px;border-radius:3px;background:{LIGHT_THEME.text_primary};display:inline-block;" title="Text"></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Apply Crisp Light",
                key="qt_set_apply_light",
                type="primary" if not is_l else "secondary",
                disabled=is_l,
                width="stretch",
            ):
                set_active_theme("light")
                st.rerun()

    # ------------------------------------------------------------------
    # Section 4: Application & Storage
    # ------------------------------------------------------------------
    with tab_storage:
        stats = store.get_overview_stats()
        rep_cnt = len(store.list_reports(limit=5000))
        prof_cnt = len(store.list_connection_profiles())

        render_section_header("Local SQLite Metadata Store", str(store.db_path))
        render_telemetry_row(
            [
                TelemetryCardData(label="Query Analyses", value=f"{stats['total_analyses']:,}", subtext="Execution & EXPLAIN records", accent=True),
                TelemetryCardData(label="Benchmark Runs", value=f"{stats['total_benchmarks']:,}", subtext="Multi-run statistics"),
                TelemetryCardData(label="A/B Comparisons", value=f"{stats['total_comparisons']:,}", subtext="Before/after diffs"),
                TelemetryCardData(label="Export Logs", value=f"{rep_cnt:,}", subtext="Report history rows"),
                TelemetryCardData(label="Saved Profiles", value=f"{prof_cnt:,}", subtext="Password-free endpoints"),
            ]
        )

        st1, st2 = st.columns([1.4, 1.0], vertical_alignment="bottom")
        hist_lim = st1.number_input(
            "Query History Display Limit",
            min_value=25,
            max_value=1000,
            value=int(st.session_state.get("qt_history_limit", 200)),
            step=25,
            key="qt_set_hist_lim",
        )
        if st2.button("Save History Limit", key="qt_set_save_hist_lim", width="stretch"):
            st.session_state["qt_history_limit"] = int(hist_lim)
            store.set_preference("history_display_limit", str(int(hist_lim)))
            st.success(f"Updated query history display limit to {int(hist_lim)} rows.")

        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        render_section_header("Maintenance", "Confirmation required before deleting local logs")
        if st.button(
            "Clear Recorded History & Benchmarks",
            key="qt_set_clear_hist_btn",
            icon=":material/delete_sweep:",
        ):
            _confirm_clear_history_dialog(store)
