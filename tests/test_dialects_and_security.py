"""Tests for multi-dialect SQLGlot engine, read-only guardrails, HMAC write consent, and credential redaction."""
from __future__ import annotations

import pytest

from src.dialects.sqlglot_engine import (
    SUPPORTED_DIALECTS,
    convert_sql_dialect,
    format_sql_for_dialect,
    parse_sql_ast,
    transpile_for_duckdb,
)
from src.security.guardrails import evaluate_sql_safety, sanitize_error_message


def test_parse_all_four_dialects():
    samples = {
        "postgresql": "SELECT employee_id, first_name FROM employees ORDER BY base_salary DESC LIMIT 5;",
        "mysql": "SELECT employee_id, DATE_FORMAT(hire_date, '%Y-%m') AS ym FROM employees LIMIT 5;",
        "sqlite": "SELECT employee_id, strftime('%Y-%m', hire_date) AS ym FROM employees LIMIT 5;",
        "sqlserver": "SELECT TOP 5 employee_id, first_name FROM employees ORDER BY base_salary DESC;",
    }
    for d in SUPPORTED_DIALECTS:
        res = parse_sql_ast(samples[d], d)
        assert res.is_valid, f"Failed parsing {d}: {res.error_message}"
        assert res.dialect == d


def test_ast_dialect_conversion_postgres_to_sqlserver_uses_top():
    pg_sql = "SELECT employee_id, first_name FROM employees ORDER BY base_salary DESC LIMIT 10;"
    conv = convert_sql_dialect(pg_sql, "postgresql", "sqlserver")
    assert conv.success
    assert "TOP 10" in conv.converted_sql.upper()


def test_ast_dialect_conversion_flags_ilike_and_returning():
    conv_ilike = convert_sql_dialect(
        "SELECT email FROM customers WHERE email ILIKE '%@acme%';",
        "postgresql",
        "mysql",
    )
    assert conv_ilike.success
    assert any("ILIKE" in w or "case-insensitive" in w.lower() for w in conv_ilike.warnings + conv_ilike.limitations)

    conv_ret = convert_sql_dialect(
        "INSERT INTO departments (department_name, region_id) VALUES ('QA', 1) RETURNING department_id;",
        "postgresql",
        "mysql",
    )
    assert conv_ret.success
    assert any("RETURNING" in l for l in conv_ret.limitations)


def test_format_sql_for_dialect_works():
    formatted, warn = format_sql_for_dialect("select a,b from tbl where a>1", "postgresql")
    assert warn is None
    assert "SELECT" in formatted
    assert "\n" in formatted


def test_transpile_tsql_top_for_duckdb():
    duck_sql, notes, err = transpile_for_duckdb(
        "SELECT TOP 5 employee_id, first_name + ' ' + last_name AS full_name, base_salary FROM employees ORDER BY base_salary DESC;",
        "sqlserver",
    )
    assert err is None
    assert "LIMIT 5" in duck_sql.upper()
    assert "||" in duck_sql
    assert len(notes) >= 1


@pytest.mark.parametrize(
    "sql,dialect",
    [
        ("INSERT INTO employees (first_name) VALUES ('X');", "postgresql"),
        ("UPDATE employees SET salary = 1 WHERE employee_id = 1;", "mysql"),
        ("DELETE FROM orders WHERE order_id = 1;", "sqlite"),
        ("DROP TABLE customers;", "sqlserver"),
        ("TRUNCATE TABLE order_items;", "postgresql"),
        ("ALTER TABLE products ADD COLUMN extra TEXT;", "postgresql"),
        ("WITH gone AS (DELETE FROM orders RETURNING order_id) SELECT * FROM gone;", "postgresql"),
        ("SELECT 1; DROP TABLE employees;", "postgresql"),
        ("SELECT pg_sleep(5);", "postgresql"),
        ("SELECT * FROM read_csv('/etc/passwd');", "postgresql"),
        ("SELECT getenv('SECRET_KEY');", "postgresql"),
        ("COPY customers TO '/tmp/out.csv';", "postgresql"),
        ("ATTACH 'evil.db' AS x;", "sqlite"),
        ("SELECT employee_id FROM employees FOR UPDATE;", "postgresql"),
    ],
)
def test_read_only_blocks_writes_ddl_admin_and_dangerous_funcs(sql: str, dialect: str):
    ev = evaluate_sql_safety(sql, dialect=dialect, allow_write_opt_in=False)
    assert not ev.allowed
    assert ev.error_message


def test_write_opt_in_requires_exact_hmac_confirmation_token():
    sql = "UPDATE employees SET salary = salary + 100 WHERE employee_id = 1;"
    step1 = evaluate_sql_safety(sql, dialect="postgresql", target_database="demo", allow_write_opt_in=True)
    assert not step1.allowed
    assert step1.requires_write_confirmation
    assert step1.confirmation_challenge is not None
    tok = step1.confirmation_challenge.token

    # Wrong SQL or target DB with same token must fail HMAC verification
    bad = evaluate_sql_safety(
        "DELETE FROM employees;",
        dialect="postgresql",
        target_database="demo",
        allow_write_opt_in=True,
        confirmed_write=True,
        confirmation_token=tok,
    )
    assert not bad.allowed

    # Exact SQL + target DB + valid token is allowed
    ok = evaluate_sql_safety(
        sql,
        dialect="postgresql",
        target_database="demo",
        allow_write_opt_in=True,
        confirmed_write=True,
        confirmation_token=tok,
    )
    assert ok.allowed
    assert not ok.is_read_only
    assert ok.operation_name == "UPDATE"


def test_sanitize_error_message_redacts_secrets():
    raw = "FATAL: password=MySecret123! in postgresql://alice:TopPass99@db.local:5432/prod token=sk-abc1234567890XYZ"
    clean = sanitize_error_message(raw)
    assert "MySecret123!" not in clean
    assert "TopPass99" not in clean
    assert "sk-abc1234567890XYZ" not in clean
    assert "[REDACTED]" in clean
