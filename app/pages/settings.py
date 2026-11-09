"""H. Settings, Database Connection Manager & Schema Explorer page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.sidebar import render_page_header
from src.config.settings import ConnectionConfig
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore


def render_settings_page() -> None:
    render_page_header(
        "Database Connection & Settings",
        "Manage local PostgreSQL connections, safety execution guardrails, and inspect database schema metadata.",
    )

    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    curr_cfg = conn_mgr.config
    status = conn_mgr.status

    tab_conn, tab_schema, tab_safety = st.tabs(
        ["PostgreSQL Connection", "Schema & Index Browser", "Safety & Execution Guardrails"]
    )

    # ------------------------------------------------------------------
    # Tab 1: Connection Manager & Profiles
    # ------------------------------------------------------------------
    with tab_conn:
        profiles = store.list_connection_profiles()
        if profiles:
            prof_names = ["-- Current / Manual --"] + [p["name"] for p in profiles]
            p_col1, p_col2, p_col3 = st.columns([2.2, 0.9, 0.9])
            chosen_prof = p_col1.selectbox("Saved Connection Profiles (Passwords Never Stored)", options=prof_names)
            if chosen_prof != "-- Current / Manual --":
                prof_data = next(p for p in profiles if p["name"] == chosen_prof)
                if p_col2.button("Load Profile", width="stretch"):
                    st.session_state["qt_cfg_host"] = prof_data["host"]
                    st.session_state["qt_cfg_port"] = int(prof_data["port"])
                    st.session_state["qt_cfg_db"] = prof_data["database_name"]
                    st.session_state["qt_cfg_user"] = prof_data["username"]
                    st.session_state["qt_cfg_ssl"] = prof_data["sslmode"]
                    st.rerun()
                if p_col3.button("Delete Profile", width="stretch"):
                    store.delete_connection_profile(chosen_prof)
                    st.rerun()

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

        c4, c5, c6 = st.columns([1.4, 1.4, 1.2])
        username = c4.text_input("Username", key="qt_cfg_user")
        password = c5.text_input("Password (Session Memory Only)", value=curr_cfg.password, type="password")
        sslmode = c6.selectbox(
            "SSL Mode",
            options=["prefer", "disable", "allow", "require"],
            key="qt_cfg_ssl",
        )

        new_cfg = ConnectionConfig(
            host=host.strip() or "localhost",
            port=int(port),
            database=database.strip() or "postgres",
            username=username.strip() or "postgres",
            password=password,
            sslmode=sslmode,
            connect_timeout=curr_cfg.connect_timeout,
        )

        b1, b2, b3, b4 = st.columns(4)
        if b1.button("Test Connection", width="stretch"):
            res = ConnectionManager.test_connection(new_cfg)
            if res.connected:
                st.success(f"Connection succeeded! {res.server_version} | Active DB: {res.current_database}")
            else:
                st.error(res.error_message)

        if b2.button("Connect", type="primary", width="stretch"):
            res = conn_mgr.connect(new_cfg)
            if res.connected:
                try:
                    conn_mgr.fetch_catalog(force_refresh=True)
                except Exception:
                    pass
                st.success(f"Connected to '{res.current_database}' on {res.config.host}:{res.config.port}.")
                st.rerun()
            else:
                st.error(res.error_message)

        if b3.button("Disconnect", width="stretch", disabled=not status.connected):
            conn_mgr.disconnect()
            st.info("Disconnected from PostgreSQL.")
            st.rerun()

        prof_name = b4.text_input("Profile Name", value="Local Sample DB", label_visibility="collapsed")
        if st.button("Save Connection Profile (No Password)"):
            store.save_connection_profile(
                name=prof_name,
                host=new_cfg.host,
                port=new_cfg.port,
                database_name=new_cfg.database,
                username=new_cfg.username,
                sslmode=new_cfg.sslmode,
                is_default=True,
            )
            st.success(f"Saved profile '{prof_name}' to local SQLite metadata (password excluded).")

        if status.connected:
            st.divider()
            st.subheader("Active Connection Telemetry & Database Switcher")
            st.markdown(f"- **Server Version:** `{status.server_version}`")
            st.markdown(f"- **Current Database:** `{status.current_database}`")
            st.markdown(f"- **Available Schemas:** `{', '.join(status.available_schemas)}`")
            if status.available_databases:
                db_sel = st.selectbox(
                    "Switch Active Database",
                    options=status.available_databases,
                    index=status.available_databases.index(status.current_database)
                    if status.current_database in status.available_databases
                    else 0,
                )
                if st.button("Switch Database"):
                    sw = conn_mgr.switch_database(db_sel)
                    if sw.connected:
                        conn_mgr.fetch_catalog(force_refresh=True)
                        st.rerun()
                    else:
                        st.error(sw.error_message)

    # ------------------------------------------------------------------
    # Tab 2: Schema & Index Browser
    # ------------------------------------------------------------------
    with tab_schema:
        if not conn_mgr.is_connected:
            st.info("Connect to PostgreSQL to inspect schemas, tables, columns, indexes, and foreign keys.")
        else:
            if st.button("Refresh Catalog Metadata"):
                conn_mgr.fetch_catalog(force_refresh=True)
            catalog = conn_mgr.fetch_catalog()
            if not catalog.tables:
                st.warning("No user tables found in this database.")
            else:
                tbl_options = [f"{t.schema_name}.{t.table_name}" for t in catalog.tables]
                chosen_tbl = st.selectbox("Select Table / View", options=tbl_options)
                sch, tbl = chosen_tbl.split(".", 1)
                tmeta = catalog.find_table(tbl, schema=sch)
                if tmeta:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Estimated Rows", f"{tmeta.estimated_rows:,}")
                    m2.metric("Table Size (MB)", f"{tmeta.table_size_bytes / (1024 * 1024):.2f}")
                    m3.metric("Index Size (MB)", f"{tmeta.index_size_bytes / (1024 * 1024):.2f}")
                    m4.metric("Seq / Index Scans", f"{tmeta.seq_scan:,} / {tmeta.idx_scan:,}")

                    st.markdown("**Columns**")
                    col_df = pd.DataFrame(
                        [
                            {
                                "#": c.ordinal_position,
                                "Column": c.column_name,
                                "Type": c.data_type,
                                "Nullable": c.is_nullable,
                                "Default": c.column_default or "",
                            }
                            for c in tmeta.columns
                        ]
                    )
                    st.dataframe(col_df, width="stretch", hide_index=True)

                    st.markdown("**Existing Indexes**")
                    if tmeta.indexes:
                        idx_df = pd.DataFrame(
                            [
                                {
                                    "Index Name": idx.index_name,
                                    "Type": idx.access_method,
                                    "Key Columns": ", ".join(idx.key_columns),
                                    "INCLUDE": ", ".join(idx.include_columns) or "-",
                                    "Unique": idx.is_unique,
                                    "Primary": idx.is_primary,
                                    "Partial WHERE": idx.predicate or "-",
                                    "idx_scan": idx.idx_scan,
                                    "Size (KB)": round(idx.size_bytes / 1024, 1),
                                }
                                for idx in tmeta.indexes
                            ]
                        )
                        st.dataframe(idx_df, width="stretch", hide_index=True)
                    else:
                        st.info("No indexes defined on this table/view.")

                    if tmeta.foreign_keys:
                        st.markdown("**Foreign Keys**")
                        fk_df = pd.DataFrame(
                            [
                                {
                                    "Constraint": fk.constraint_name,
                                    "Columns": ", ".join(fk.columns),
                                    "References": f"{fk.referenced_table}({', '.join(fk.referenced_columns)})",
                                }
                                for fk in tmeta.foreign_keys
                            ]
                        )
                        st.dataframe(fk_df, width="stretch", hide_index=True)

    # ------------------------------------------------------------------
    # Tab 3: Safety & Execution Guardrails
    # ------------------------------------------------------------------
    with tab_safety:
        t_ms = st.number_input(
            "Default Statement Timeout (ms)",
            min_value=100,
            max_value=60000,
            value=int(st.session_state["qt_timeout_ms"]),
            step=500,
        )
        m_rows = st.number_input(
            "Default Maximum Returned Rows",
            min_value=10,
            max_value=5000,
            value=int(st.session_state["qt_max_rows"]),
            step=50,
        )
        def_analyze = st.checkbox(
            "Default to EXPLAIN (ANALYZE, BUFFERS) when connected",
            value=bool(st.session_state["qt_explain_analyze"]),
        )
        if st.button("Save Safety Preferences", type="primary"):
            st.session_state["qt_timeout_ms"] = int(t_ms)
            st.session_state["qt_max_rows"] = int(m_rows)
            st.session_state["qt_explain_analyze"] = bool(def_analyze)
            store.set_preference("statement_timeout_ms", str(int(t_ms)))
            store.set_preference("max_rows", str(int(m_rows)))
            store.set_preference("explain_analyze_default", "true" if def_analyze else "false")
            st.success("Guardrail preferences saved to local SQLite metadata.")
