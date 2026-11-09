"""Tests for Demo sandbox, SQL/dump AST importer, CSV/Excel/JSON importers, and live SQLite connector."""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from openpyxl import Workbook

from src.connectors.adapters import LiveConnectionRequest, MultiDBConnector
from src.connectors.demo_sandbox import ensure_demo_duckdb, ensure_sample_export_files
from src.context.context_manager import ActiveContextManager
from src.importers.sql_dump_importer import accept_sql_import, preview_sql_import
from src.importers.tabular_importer import (
    accept_tabular_import,
    preview_csv_import,
    preview_excel_import,
    preview_json_import,
)


def test_demo_duckdb_and_sample_exports_exist_and_query():
    db_path = ensure_demo_duckdb()
    assert db_path.exists()

    samples = ensure_sample_export_files()
    assert {"sql", "csv", "json", "xlsx"}.issubset(samples.keys())
    for p in samples.values():
        assert p.exists() and p.stat().st_size > 50

    conn = MultiDBConnector()
    snap = conn.activate_demo_sandbox()
    tbl_names = set(snap.all_table_names())
    assert {"sales_regions", "departments", "employees", "customers", "products", "orders", "order_items"}.issubset(tbl_names)
    assert len(snap.relationships) >= 5

    res = conn.execute_sql("SELECT COUNT(*) AS cnt FROM employees;")
    assert res.success
    assert res.rows[0]["cnt"] == 16


def test_sql_dump_importer_safely_strips_metacommands_and_loads_sandbox(tmp_path: Path):
    sql_dump = """
    \\connect prod_db
    SET statement_timeout = 0;
    LOCK TABLE accounts WRITE;
    COPY legacy_log FROM stdin;
    1\told_entry
    \\.
    CREATE TABLE accounts (
        account_id INT PRIMARY KEY,
        owner_name VARCHAR(100) NOT NULL,
        balance NUMERIC(12,2)
    );
    CREATE TABLE ledger_entries (
        entry_id INT PRIMARY KEY,
        account_id INT REFERENCES accounts(account_id),
        amount NUMERIC(10,2) NOT NULL
    );
    INSERT INTO accounts (account_id, owner_name, balance) VALUES
        (1, 'Asha', 1200.50),
        (2, 'Vikram', 450.00);
    INSERT INTO ledger_entries (entry_id, account_id, amount) VALUES
        (10, 1, 200.50);
    """
    prev = preview_sql_import(sql_dump, "company_backup.dump", dialect="postgresql")
    assert prev.file_kind == "dump"
    assert {t.name for t in prev.tables} == {"accounts", "ledger_entries"}
    assert len(prev.relationships) == 1
    assert any("COPY" in u or "\\connect" in u or "SET" in u for u in prev.ambiguous_or_unsupported)

    out_db = accept_sql_import(prev, tmp_path)
    assert out_db.exists()

    ctx_mgr = ActiveContextManager(sandbox_dir=tmp_path)
    snap = ctx_mgr.connector.activate_uploaded_duckdb(
        out_db,
        label="Dump Sandbox",
        context_id="dump_1",
        relationships=prev.relationships,
    )
    assert snap.find_table("accounts") is not None
    q = ctx_mgr.connector.execute_sql("SELECT owner_name, balance FROM accounts ORDER BY account_id;")
    assert q.success
    assert q.rows == [{"owner_name": "Asha", "balance": 1200.5}, {"owner_name": "Vikram", "balance": 450.0}]


def test_csv_excel_and_json_importers_never_fabricate_foreign_keys(tmp_path: Path):
    # 1. CSV
    csv_bytes = b"order_id,region,amount,order_date\n1,North,100.50,2026-01-10\n2,South,250.00,2026-02-15\n"
    prev_csv, ds_csv = preview_csv_import(csv_bytes, "regional_orders.csv")
    assert len(prev_csv.tables) == 1
    assert prev_csv.relationships == []
    assert any("foreign-key" in m.lower() for m in prev_csv.ambiguous_or_unsupported)
    db_csv = accept_tabular_import(prev_csv, ds_csv, tmp_path)
    assert db_csv.exists()

    # 2. Excel (.xlsx)
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["sku", "price", "active"])
    ws.append(["SKU-1", 49.99, True])
    ws.append(["SKU-2", 99.00, False])
    buf = io.BytesIO()
    wb.save(buf)
    prev_xl, ds_xl = preview_excel_import(buf.getvalue(), "catalog.xlsx")
    assert prev_xl.tables[0].name == "products"
    assert prev_xl.relationships == []
    db_xl = accept_tabular_import(prev_xl, ds_xl, tmp_path)
    assert db_xl.exists()

    # 3. JSON
    json_bytes = b'[{"id": 1, "city": "Bengaluru", "score": 9.5}, {"id": 2, "city": "Austin", "score": 8.2}]'
    prev_js, ds_js = preview_json_import(json_bytes, "cities.json")
    assert prev_js.tables[0].name == "cities"
    assert prev_js.relationships == []
    db_js = accept_tabular_import(prev_js, ds_js, tmp_path)
    assert db_js.exists()

    mgr = ActiveContextManager(sandbox_dir=tmp_path)
    mgr.connector.activate_uploaded_duckdb(db_js, label="Cities", context_id="cities")
    res = mgr.connector.execute_sql("SELECT city FROM cities ORDER BY score DESC LIMIT 1;")
    assert res.success and res.rows[0]["city"] == "Bengaluru"


def test_live_sqlite_connector_read_only_inspection_and_execution(tmp_path: Path):
    sqlite_file = tmp_path / "inventory.sqlite"
    con = sqlite3.connect(str(sqlite_file))
    try:
        con.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE suppliers (supplier_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE parts (
                part_id INTEGER PRIMARY KEY,
                supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id),
                cost REAL NOT NULL
            );
            INSERT INTO suppliers VALUES (1, 'Apex Foundry'), (2, 'Nova Precision');
            INSERT INTO parts VALUES (10, 1, 14.5), (11, 2, 22.0);
            """
        )
        con.commit()
    finally:
        con.close()

    conn = MultiDBConnector()
    snap = conn.connect_live(
        LiveConnectionRequest(engine="sqlite", sqlite_path=str(sqlite_file), allow_write_opt_in=False)
    )
    assert snap.source_kind == "live_sqlite"
    assert snap.dialect == "sqlite"
    assert {t.name for t in snap.tables} == {"parts", "suppliers"}
    assert len(snap.relationships) == 1

    # Read-only query succeeds
    ok = conn.execute_sql("SELECT p.part_id, s.name FROM parts p JOIN suppliers s ON s.supplier_id = p.supplier_id ORDER BY p.part_id;")
    assert ok.success and ok.rows_returned == 2

    # Write blocked by default
    blocked = conn.execute_sql("DELETE FROM parts WHERE part_id = 10;")
    assert not blocked.success
    assert "Read-Only" in blocked.error_message
