"""Built-in deterministic DuckDB demo database & sample data files.

Designed so a new user can explore NL-to-SQL, debugging, optimization,
multi-dialect conversion, and file imports immediately with zero external DB setup.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
from openpyxl import Workbook

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SANDBOX_DIR = PROJECT_ROOT / "data" / "sandboxes"
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"


def ensure_demo_duckdb(db_path: Path | None = None) -> Path:
    """Create (if absent) and return path to the deterministic Enterprise HR & Sales Demo DuckDB."""
    target = db_path or (SANDBOX_DIR / "demo_enterprise.duckdb")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 8192:
        # Quick health check that core tables are populated
        con = duckdb.connect(str(target), read_only=True)
        try:
            tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
            if {"departments", "employees", "sales_regions", "customers", "products", "orders", "order_items"} <= tables:
                cnt = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
                if cnt >= 200:
                    return target
        except Exception:
            pass
        finally:
            con.close()
        target.unlink(missing_ok=True)

    rng = random.Random(2026)
    con = duckdb.connect(str(target))
    try:
        con.execute("""
            CREATE TABLE sales_regions (
                region_id INTEGER PRIMARY KEY,
                region_name VARCHAR NOT NULL UNIQUE,
                country VARCHAR NOT NULL,
                director_name VARCHAR NOT NULL
            );

            CREATE TABLE departments (
                department_id INTEGER PRIMARY KEY,
                department_name VARCHAR NOT NULL UNIQUE,
                cost_center VARCHAR NOT NULL,
                annual_budget DOUBLE NOT NULL
            );

            CREATE TABLE employees (
                employee_id INTEGER PRIMARY KEY,
                first_name VARCHAR NOT NULL,
                last_name VARCHAR NOT NULL,
                email VARCHAR NOT NULL UNIQUE,
                department_id INTEGER NOT NULL REFERENCES departments(department_id),
                region_id INTEGER NOT NULL REFERENCES sales_regions(region_id),
                job_title VARCHAR NOT NULL,
                hire_date DATE NOT NULL,
                base_salary DOUBLE NOT NULL,
                sales_target DOUBLE NOT NULL
            );

            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                customer_name VARCHAR NOT NULL,
                email VARCHAR NOT NULL,
                country VARCHAR NOT NULL,
                city VARCHAR NOT NULL,
                segment VARCHAR NOT NULL,
                signup_date DATE NOT NULL
            );

            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                sku VARCHAR NOT NULL UNIQUE,
                product_name VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                unit_price DOUBLE NOT NULL,
                unit_cost DOUBLE NOT NULL,
                is_active BOOLEAN NOT NULL
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
                region_id INTEGER NOT NULL REFERENCES sales_regions(region_id),
                order_date DATE NOT NULL,
                status VARCHAR NOT NULL,
                subtotal_amount DOUBLE NOT NULL,
                discount_amount DOUBLE NOT NULL,
                total_amount DOUBLE NOT NULL
            );

            CREATE TABLE order_items (
                order_item_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(order_id),
                product_id INTEGER NOT NULL REFERENCES products(product_id),
                quantity INTEGER NOT NULL,
                unit_price DOUBLE NOT NULL,
                line_total DOUBLE NOT NULL
            );
        """)

        regions = [
            (1, "North America", "USA", "Claire Bennett"),
            (2, "Europe West", "Germany", "Lukas Weber"),
            (3, "Asia Pacific", "India", "Ananya Rao"),
            (4, "Latin America", "Brazil", "Mateo Silva"),
        ]
        con.executemany("INSERT INTO sales_regions VALUES (?, ?, ?, ?)", regions)

        departments = [
            (1, "Enterprise Sales", "CC-101", 950000.0),
            (2, "Mid-Market Sales", "CC-102", 680000.0),
            (3, "Strategic Accounts", "CC-103", 1100000.0),
            (4, "Channel Partners", "CC-104", 490000.0),
        ]
        con.executemany("INSERT INTO departments VALUES (?, ?, ?, ?)", departments)

        first_names = [
            "Aarav", "Maya", "Liam", "Sofia", "Noah", "Priya", "Ethan", "Nadia",
            "Rohan", "Hannah", "Lucas", "Kavya", "Owen", "Elena", "Vikram", "Zara",
        ]
        last_names = [
            "Sharma", "Patel", "Carter", "Lindqvist", "Kim", "Nair", "Brooks", "Rossi",
            "Mehta", "Foster", "Almeida", "Iyer", "Hughes", "Bauer", "Menon", "Cooper",
        ]
        employees_rows = []
        for idx in range(1, 17):
            fn = first_names[idx - 1]
            ln = last_names[idx - 1]
            dept_id = ((idx - 1) % 4) + 1
            reg_id = ((idx - 1) % 4) + 1
            title = "Senior Account Executive" if idx <= 6 else ("Account Executive" if idx <= 12 else "Sales Specialist")
            hire = date(2021 + (idx % 4), ((idx * 2) % 12) + 1, min(28, idx + 3))
            salary = 62000.0 + (idx % 5) * 8500.0
            target = 35000.0 + (idx % 4) * 12000.0
            employees_rows.append((
                idx,
                fn,
                ln,
                f"{fn.lower()}.{ln.lower()}@querytrellis-demo.local",
                dept_id,
                reg_id,
                title,
                hire,
                salary,
                target,
            ))
        con.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", employees_rows)

        # Customers (including deliberate duplicate customer emails & names for deduplication queries!)
        cust_rows = []
        cities = [
            ("USA", "Austin"), ("USA", "Seattle"), ("Germany", "Berlin"),
            ("India", "Bengaluru"), ("India", "Pune"), ("Brazil", "Sao Paulo"),
        ]
        segments = ["enterprise", "mid_market", "smb", "startup"]
        for cid in range(1, 41):
            country, city = cities[(cid - 1) % len(cities)]
            cname = f"Customer {cid:02d} Corp"
            cmail = f"buyer{cid:02d}@clientorg.example"
            # Introduce deterministic duplicate emails/names at IDs 37-40 matching IDs 1-4
            if cid >= 37:
                orig_idx = cid - 36
                cname = f"Customer {orig_idx:02d} Corp"
                cmail = f"buyer{orig_idx:02d}@clientorg.example"
                country, city = cities[(orig_idx - 1) % len(cities)]
            cust_rows.append((
                cid,
                cname,
                cmail,
                country,
                city,
                segments[(cid - 1) % len(segments)],
                date(2024, ((cid - 1) % 12) + 1, min(28, cid)),
            ))
        con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", cust_rows)

        # Products (Products 7 and 8 deliberately trend downward in recent months for "declining sales" queries)
        products = [
            (1, "SKU-101", "CloudWarehouse Pro", "Analytics", 1200.0, 420.0, True),
            (2, "SKU-102", "StreamPulse Connector", "Integration", 650.0, 210.0, True),
            (3, "SKU-103", "VaultGuard Compliance", "Security", 980.0, 340.0, True),
            (4, "SKU-104", "MetricMesh BI Suite", "Analytics", 840.0, 290.0, True),
            (5, "SKU-105", "EdgeSync Runtime", "Infrastructure", 520.0, 190.0, True),
            (6, "SKU-106", "QueryCache Accelerator", "Performance", 760.0, 240.0, True),
            (7, "SKU-107", "LegacyBatch Exporter", "Integration", 450.0, 200.0, True),
            (8, "SKU-108", "DesktopReport v1", "Reporting", 320.0, 150.0, True),
        ]
        con.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", products)

        # Orders across 6 recent months (2025-10 through 2026-03) relative to realistic fixed anchor
        months = [
            date(2025, 10, 1),
            date(2025, 11, 1),
            date(2025, 12, 1),
            date(2026, 1, 1),
            date(2026, 2, 1),
            date(2026, 3, 1),
        ]
        order_rows = []
        item_rows = []
        oid = 1
        iid = 1
        statuses = ["completed", "completed", "completed", "completed", "shipped", "cancelled"]
        for m_idx, month_start in enumerate(months):
            # 45 orders per month -> 270 orders total
            for k in range(45):
                # Skew repeat customers so multiple customers purchase >3 times
                cid = ((k * 3 + m_idx) % 28) + 1
                # Skew top employees smoothly (emp 1..6 perform higher than 7..16)
                emp_pool = [1, 2, 3, 4, 5, 6, 1, 2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
                eid = emp_pool[(k + m_idx) % len(emp_pool)]
                reg_id = ((eid - 1) % 4) + 1
                day_offset = (k * 17 + m_idx * 3) % 27
                odate = month_start + timedelta(days=day_offset)
                status = statuses[(k + m_idx) % len(statuses)]

                # Pick 1-2 line items
                if k % 5 == 0 and m_idx >= 3:
                    # Products 1-4 grow in recent months while 7-8 decline smoothly
                    prod_id = ((k + m_idx) % 4) + 1
                elif m_idx <= 1:
                    prod_id = ((k + m_idx) % 8) + 1
                elif m_idx in (2, 3):
                    prod_id = ((k + m_idx) % 7) + 1
                else:
                    prod_id = ((k + m_idx) % 6) + 1

                qty = 1 + ((k + eid + m_idx) % 4)
                if prod_id in (7, 8):
                    qty = max(1, 5 - m_idx)
                elif prod_id in (1, 2, 3):
                    qty = 1 + ((m_idx + k) % 4)

                uprice = products[prod_id - 1][4]
                sub = round(uprice * qty, 2)
                disc = round(sub * (0.05 if k % 4 == 0 else 0.0), 2)
                tot = round(sub - disc, 2)

                order_rows.append((oid, cid, eid, reg_id, odate, status, sub, disc, tot))
                item_rows.append((iid, oid, prod_id, qty, uprice, tot))
                iid += 1

                # Extra line item on every 3rd order
                if k % 3 == 0:
                    prod2 = 6 if prod_id != 6 else 4
                    qty2 = 1 + (rng.randint(0, 2))
                    p2 = products[prod2 - 1][4]
                    lt2 = round(p2 * qty2, 2)
                    item_rows.append((iid, oid, prod2, qty2, p2, lt2))
                    iid += 1
                    order_rows[-1] = (oid, cid, eid, reg_id, odate, status, round(sub + lt2, 2), disc, round(tot + lt2, 2))

                oid += 1

        con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", order_rows)
        con.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)", item_rows)
    finally:
        con.close()
    return target


def ensure_sample_export_files(output_dir: Path | None = None) -> dict[str, Path]:
    """Generate curated .sql, .csv, .xlsx, and .json sample datasets for upload testing."""
    target_dir = output_dir or SAMPLE_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    sql_file = target_dir / "hr_sales_schema.sql"
    if not sql_file.exists():
        sql_file.write_text(
            """-- QueryTrellis Sample Enterprise Analytics SQL Schema & Seed
CREATE TABLE departments (
    department_id INTEGER PRIMARY KEY,
    department_name VARCHAR(80) NOT NULL UNIQUE,
    annual_budget NUMERIC(12, 2) NOT NULL
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(160) NOT NULL UNIQUE,
    department_id INTEGER NOT NULL REFERENCES departments(department_id),
    salary NUMERIC(10, 2) NOT NULL,
    sales_target NUMERIC(12, 2) NOT NULL
);

CREATE TABLE quarterly_deals (
    deal_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
    region VARCHAR(60) NOT NULL,
    closed_at DATE NOT NULL,
    deal_amount NUMERIC(12, 2) NOT NULL,
    profit_margin NUMERIC(5, 2) NOT NULL
);

INSERT INTO departments (department_id, department_name, annual_budget) VALUES
(1, 'Enterprise Sales', 950000.00),
(2, 'Strategic Accounts', 1100000.00),
(3, 'Channel Partners', 490000.00);

INSERT INTO employees (employee_id, full_name, email, department_id, salary, sales_target) VALUES
(1, 'Aarav Sharma', 'aarav@demo.local', 1, 85000.00, 120000.00),
(2, 'Maya Patel', 'maya@demo.local', 2, 92000.00, 150000.00),
(3, 'Liam Carter', 'liam@demo.local', 1, 79000.00, 110000.00),
(4, 'Sofia Lindqvist', 'sofia@demo.local', 3, 74000.00, 95000.00);

INSERT INTO quarterly_deals (deal_id, employee_id, region, closed_at, deal_amount, profit_margin) VALUES
(101, 1, 'Asia Pacific', '2026-01-15', 45000.00, 0.34),
(102, 2, 'North America', '2026-01-22', 62000.00, 0.39),
(103, 1, 'Asia Pacific', '2026-02-11', 54000.00, 0.36),
(104, 3, 'Europe West', '2026-02-19', 38000.00, 0.28),
(105, 4, 'Europe West', '2026-03-04', 41000.00, 0.31),
(106, 2, 'North America', '2026-03-14', 71000.00, 0.41);
""",
            encoding="utf-8",
        )
    paths["sql"] = sql_file

    csv_file = target_dir / "monthly_revenue.csv"
    if not csv_file.exists():
        rows = [
            ["month", "region", "orders_count", "gross_revenue", "net_revenue", "active_customers"],
            ["2025-10-01", "North America", 42, 89400.50, 84210.00, 29],
            ["2025-11-01", "North America", 46, 94120.00, 89600.00, 31],
            ["2025-12-01", "North America", 51, 108500.00, 101900.00, 35],
            ["2026-01-01", "North America", 48, 99200.00, 94310.00, 33],
            ["2026-02-01", "North America", 52, 112400.00, 106800.00, 37],
            ["2026-03-01", "North America", 57, 124950.00, 118900.00, 41],
            ["2025-10-01", "Asia Pacific", 35, 67200.00, 64100.00, 24],
            ["2025-11-01", "Asia Pacific", 39, 73800.00, 70450.00, 26],
            ["2025-12-01", "Asia Pacific", 44, 83900.00, 79800.00, 30],
            ["2026-01-01", "Asia Pacific", 41, 78500.00, 74900.00, 28],
            ["2026-02-01", "Asia Pacific", 47, 91200.00, 87100.00, 32],
            ["2026-03-01", "Asia Pacific", 53, 103600.00, 98750.00, 36],
        ]
        with csv_file.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
    paths["csv"] = csv_file

    json_file = target_dir / "product_catalog.json"
    if not json_file.exists():
        payload = [
            {"product_id": 1, "sku": "SKU-101", "name": "CloudWarehouse Pro", "category": "Analytics", "unit_price": 1200.0, "discontinued": False},
            {"product_id": 2, "sku": "SKU-102", "name": "StreamPulse Connector", "category": "Integration", "unit_price": 650.0, "discontinued": False},
            {"product_id": 3, "sku": "SKU-103", "name": "VaultGuard Compliance", "category": "Security", "unit_price": 980.0, "discontinued": False},
            {"product_id": 4, "sku": "SKU-107", "name": "LegacyBatch Exporter", "category": "Integration", "unit_price": 450.0, "discontinued": True},
        ]
        json_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paths["json"] = json_file

    xlsx_file = target_dir / "regional_targets.xlsx"
    if not xlsx_file.exists():
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "regional_quotas"
        ws1.append(["region_id", "region_name", "quarter", "revenue_quota", "headcount"])
        ws1.append([1, "North America", "2026-Q1", 320000, 14])
        ws1.append([2, "Europe West", "2026-Q1", 250000, 10])
        ws1.append([3, "Asia Pacific", "2026-Q1", 280000, 12])
        ws1.append([4, "Latin America", "2026-Q1", 160000, 6])

        ws2 = wb.create_sheet("rep_incentives")
        ws2.append(["tier_id", "tier_name", "min_quota_pct", "bonus_pct"])
        ws2.append([1, "Baseline", 0.80, 0.05])
        ws2.append([2, "Target", 1.00, 0.10])
        ws2.append([3, "Accelerator", 1.20, 0.16])
        wb.save(xlsx_file)
    paths["xlsx"] = xlsx_file

    return paths
