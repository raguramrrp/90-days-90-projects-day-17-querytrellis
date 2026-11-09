"""Unit tests for PostgreSQL connection error translation and SQLite metadata store."""
from __future__ import annotations

from src.config.settings import ConnectionConfig
from src.db.connection_manager import ConnectionManager, translate_pg_error
from src.db.metadata_store import MetadataStore


def test_translate_pg_error_produces_friendly_messages() -> None:
    cfg = ConnectionConfig(host="localhost", port=5432, database="missing_db", username="postgres", password="secret")

    msg_auth = translate_pg_error(Exception("FATAL: password authentication failed for user \"postgres\""), cfg)
    assert "Authentication failed" in msg_auth
    assert "secret" not in msg_auth

    msg_db = translate_pg_error(Exception('FATAL: database "missing_db" does not exist'), cfg)
    assert "does not exist" in msg_db

    msg_refused = translate_pg_error(Exception("connection to server at localhost failed: Connection refused"), cfg)
    assert "Cannot reach PostgreSQL" in msg_refused

    msg_timeout = translate_pg_error(Exception("canceling statement due to statement timeout"), cfg)
    assert "statement timeout" in msg_timeout.lower()


def test_test_connection_handles_unreachable_port() -> None:
    bad_cfg = ConnectionConfig(host="127.0.0.1", port=59999, database="postgres", username="postgres", connect_timeout=1)
    status = ConnectionManager.test_connection(bad_cfg)
    assert status.connected is False
    assert status.error_message != ""


def test_metadata_store_roundtrip_and_no_password_storage(temp_store: MetadataStore) -> None:
    temp_store.save_connection_profile(
        name="Local Sample",
        host="localhost",
        port=5432,
        database_name="querytrellis_sample",
        username="postgres",
        is_default=True,
    )
    profs = temp_store.list_connection_profiles()
    assert len(profs) == 1
    assert "password" not in profs[0]

    aid = temp_store.save_analysis(
        database_name="querytrellis_sample",
        sql_text="SELECT * FROM orders",
        sql_hash="hash1",
        status="success",
        execution_mode="explain_analyze",
        pg_execution_ms=12.4,
        antipatterns_json=[{"issue_name": "Wildcard Projection (SELECT *)"}],
    )
    fetched = temp_store.get_analysis(aid)
    assert fetched is not None
    assert fetched["pg_execution_ms"] == 12.4

    stats = temp_store.get_overview_stats()
    assert stats["total_analyses"] == 1
    assert stats["common_issues"][0]["issue_name"] == "Wildcard Projection (SELECT *)"

    temp_store.set_preference("max_rows", "250")
    assert temp_store.get_preference("max_rows") == "250"
