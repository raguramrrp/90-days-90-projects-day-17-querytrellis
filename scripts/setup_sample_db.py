"""Deterministic synthetic e-commerce database creator and seeder for QueryTrellis.

Creates the target database (if absent), applies ``sql/schema.sql``, bulk-loads
deterministic synthetic records via PostgreSQL COPY, resets sequences, and runs
ANALYZE so planner statistics accurately reflect the dataset.

Default volumes:
  - categories  :     25
  - customers   : 12,000
  - products    :  2,500
  - orders      : 55,000
  - order_items :120,000
  - payments    : 45,000
  - shipments   : 35,000
  - reviews     : 12,000
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg import sql as pg_sql
from psycopg.conninfo import make_conninfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import ConnectionConfig, load_settings
from src.db.connection_manager import translate_pg_error

FIRST_NAMES = [
    "Aarav", "Ananya", "Vihaan", "Diya", "Rohan", "Priya", "Karthik", "Meera",
    "Arjun", "Sneha", "Vikram", "Nandini", "Siddharth", "Kavya", "Aditya", "Pooja",
    "Rahul", "Shreya", "Nikhil", "Ishita", "Liam", "Emma", "Noah", "Olivia",
    "Ethan", "Sophia", "Mason", "Ava", "Lucas", "Mia",
]
LAST_NAMES = [
    "Sharma", "Patel", "Reddy", "Nair", "Iyer", "Verma", "Gupta", "Mehta",
    "Kulkarni", "Joshi", "Rao", "Singh", "Menon", "Das", "Bhat", "Chatterjee",
    "Smith", "Johnson", "Brown", "Taylor", "Anderson", "Thomas", "Moore", "Martin",
]
COUNTRIES_CITIES = [
    ("India", ["Bengaluru", "Chennai", "Mumbai", "Hyderabad", "Pune", "Delhi"]),
    ("United States", ["Austin", "Seattle", "Chicago", "Boston", "San Jose"]),
    ("United Kingdom", ["London", "Manchester", "Bristol", "Edinburgh"]),
    ("Germany", ["Berlin", "Munich", "Hamburg", "Frankfurt"]),
    ("Singapore", ["Singapore"]),
    ("Canada", ["Toronto", "Vancouver", "Montreal"]),
]
SEGMENTS = ["consumer", "consumer", "consumer", "smb", "smb", "enterprise", "vip"]
BRANDS = [
    "VoltEdge", "NorthStar", "Kinetix", "PureCraft", "ApexGear", "Lumina",
    "AeroTech", "UrbanNest", "Boreal", "CrestLine", "Veloce", "ZenithWorks",
]
PRODUCT_NOUNS = [
    "Wireless Mouse", "Mechanical Keyboard", "USB-C Hub", "Studio Monitor",
    "Running Shoes", "Backpack", "Water Bottle", "Desk Lamp", "Coffee Grinder",
    "Noise-Cancelling Headphones", "SSD Enclosure", "Smart Plug", "Yoga Mat",
    "Stainless Kettle", "Notebook Set", "Ergonomic Chair",
]
ORDER_STATUSES = [
    "delivered", "delivered", "delivered", "delivered",
    "shipped", "shipped",
    "processing",
    "pending",
    "cancelled",
    "returned",
]
SALES_CHANNELS = ["web", "web", "mobile", "mobile", "marketplace", "api"]
PAYMENT_METHODS = ["card", "upi", "upi", "netbanking", "wallet", "cod"]
PAYMENT_STATUSES = ["captured", "captured", "captured", "captured", "authorized", "failed", "refunded"]
CARRIERS = ["BlueDart", "Delhivery", "DHL", "FedEx", "IndiaPost"]
SHIPMENT_STATUSES = ["delivered", "delivered", "delivered", "in_transit", "out_for_delivery", "label_created", "delayed"]

CATEGORY_DEFS = [
    (1, "Electronics", None, "electronics"),
    (2, "Home & Kitchen", None, "home-kitchen"),
    (3, "Sports & Fitness", None, "sports-fitness"),
    (4, "Office & Stationery", None, "office-stationery"),
    (5, "Accessories", None, "accessories"),
    (6, "Audio & Headphones", 1, "audio-headphones"),
    (7, "Keyboards & Mice", 1, "keyboards-mice"),
    (8, "Storage & Drives", 1, "storage-drives"),
    (9, "Smart Home", 1, "smart-home"),
    (10, "Monitors & Displays", 1, "monitors-displays"),
    (11, "Coffee & Beverage", 2, "coffee-beverage"),
    (12, "Lighting", 2, "lighting"),
    (13, "Drinkware", 2, "drinkware"),
    (14, "Kitchen Appliances", 2, "kitchen-appliances"),
    (15, "Running & Footwear", 3, "running-footwear"),
    (16, "Yoga & Mobility", 3, "yoga-mobility"),
    (17, "Travel & Backpacks", 3, "travel-backpacks"),
    (18, "Ergonomic Furniture", 4, "ergonomic-furniture"),
    (19, "Paper & Notebooks", 4, "paper-notebooks"),
    (20, "Desk Organizers", 4, "desk-organizers"),
    (21, "Cables & Adapters", 5, "cables-adapters"),
    (22, "Laptop Sleeves", 5, "laptop-sleeves"),
    (23, "Chargers & Power", 5, "chargers-power"),
    (24, "Networking", 1, "networking"),
    (25, "Wearables", 1, "wearables"),
]


def _make_admin_conninfo(cfg: ConnectionConfig, dbname: str = "postgres") -> str:
    params = {
        "host": cfg.host,
        "port": cfg.port,
        "dbname": dbname,
        "user": cfg.username,
        "sslmode": cfg.sslmode,
        "connect_timeout": cfg.connect_timeout,
    }
    if cfg.password:
        params["password"] = cfg.password
    return make_conninfo(**params)


def ensure_database_exists(cfg: ConnectionConfig) -> None:
    """Create the target PostgreSQL database if it does not already exist."""
    admin_info = _make_admin_conninfo(cfg, dbname="postgres")
    with psycopg.connect(admin_info, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg.database,))
            exists = cur.fetchone() is not None
            if not exists:
                cur.execute(
                    pg_sql.SQL("CREATE DATABASE {}").format(pg_sql.Identifier(cfg.database))
                )
                print(f"[OK] Created database '{cfg.database}'.")
            else:
                print(f"[OK] Database '{cfg.database}' already exists.")


def seed_sample_database(
    cfg: ConnectionConfig,
    *,
    scale: float = 1.0,
    reset: bool = False,
    seed: int = 42,
) -> dict[str, int]:
    """Apply schema.sql and deterministically seed all 8 e-commerce tables."""
    t_start = time.perf_counter()
    ensure_database_exists(cfg)

    rng = random.Random(seed)
    n_customers = max(100, int(round(12000 * scale)))
    n_products = max(50, int(round(2500 * scale)))
    n_orders = max(300, int(round(55000 * scale)))
    n_items = max(600, int(round(120000 * scale)))
    n_payments = max(250, int(round(45000 * scale)))
    n_shipments = max(200, int(round(35000 * scale)))
    n_reviews = max(100, int(round(12000 * scale)))

    schema_path = PROJECT_ROOT / "sql" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    target_info = _make_admin_conninfo(cfg, dbname=cfg.database)
    base_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    span_seconds = 730 * 86400  # 2 years deterministic span (2024-2025/early 2026)

    with psycopg.connect(target_info, autocommit=False) as conn:
        with conn.cursor() as cur:
            if reset:
                cur.execute(
                    "DROP TABLE IF EXISTS reviews, shipments, payments, order_items, "
                    "orders, products, customers, categories CASCADE;"
                )
            cur.execute(schema_sql)

            # Check if already populated when not resetting
            cur.execute("SELECT COUNT(*) FROM orders")
            existing_orders = int(cur.fetchone()[0])  # type: ignore[index]
            if existing_orders > 0 and not reset:
                print(
                    f"[INFO] Database already contains {existing_orders:,} orders. "
                    "Pass --reset to recreate and reseed from scratch."
                )
                counts = {}
                for tbl in ("categories", "customers", "products", "orders", "order_items", "payments", "shipments", "reviews"):
                    cur.execute(pg_sql.SQL("SELECT COUNT(*) FROM {}").format(pg_sql.Identifier(tbl)))
                    counts[tbl] = int(cur.fetchone()[0])  # type: ignore[index]
                conn.commit()
                return counts

            print("[*] Seeding categories (25)...")
            with cur.copy(
                "COPY categories (category_id, category_name, parent_category_id, slug, created_at) FROM STDIN"
            ) as cp:
                for cid, cname, parent_id, slug in CATEGORY_DEFS:
                    cp.write_row((cid, cname, parent_id, slug, base_dt))

            print(f"[*] Seeding customers ({n_customers:,})...")
            customer_countries: list[str] = []
            with cur.copy(
                "COPY customers (customer_id, first_name, last_name, email, country, city, segment, is_active, created_at) FROM STDIN"
            ) as cp:
                for cid in range(1, n_customers + 1):
                    fn = rng.choice(FIRST_NAMES)
                    ln = rng.choice(LAST_NAMES)
                    country, cities = rng.choice(COUNTRIES_CITIES)
                    customer_countries.append(country)
                    city = rng.choice(cities)
                    seg = rng.choice(SEGMENTS)
                    is_active = rng.random() > 0.08
                    created = base_dt + timedelta(seconds=rng.randint(0, span_seconds // 2))
                    email = f"customer{cid}@example.com"
                    cp.write_row((cid, fn, ln, email, country, city, seg, is_active, created))

            print(f"[*] Seeding products ({n_products:,})...")
            product_prices: list[float] = []
            with cur.copy(
                "COPY products (product_id, category_id, sku, product_name, brand, unit_price, cost_price, stock_quantity, is_discontinued, created_at) FROM STDIN"
            ) as cp:
                for pid in range(1, n_products + 1):
                    cat_id = rng.randint(1, len(CATEGORY_DEFS))
                    brand = rng.choice(BRANDS)
                    noun = rng.choice(PRODUCT_NOUNS)
                    price = round(rng.uniform(8.0, 950.0), 2)
                    product_prices.append(price)
                    cost = round(price * rng.uniform(0.45, 0.78), 2)
                    stock = rng.randint(0, 500)
                    disc = rng.random() < 0.05
                    sku = f"SKU-{cat_id:02d}-{pid:05d}"
                    pname = f"{brand} {noun} {pid % 100:02d}"
                    cp.write_row((pid, cat_id, sku, pname, brand, price, cost, stock, disc, base_dt))

            print(f"[*] Seeding orders ({n_orders:,})...")
            order_dates: list[datetime] = []
            order_totals: list[float] = []
            order_statuses: list[str] = []
            with cur.copy(
                "COPY orders (order_id, customer_id, order_date, status, shipping_country, subtotal_amount, discount_amount, total_amount, sales_channel) FROM STDIN"
            ) as cp:
                for oid in range(1, n_orders + 1):
                    cust_id = rng.randint(1, n_customers)
                    odate = base_dt + timedelta(seconds=rng.randint(0, span_seconds))
                    status = rng.choice(ORDER_STATUSES)
                    country = customer_countries[cust_id - 1]
                    subtotal = round(rng.uniform(20.0, 1800.0), 2)
                    disc = round(subtotal * rng.choice([0.0, 0.0, 0.05, 0.10, 0.15]), 2)
                    total = round(max(0.0, subtotal - disc), 2)
                    channel = rng.choice(SALES_CHANNELS)
                    order_dates.append(odate)
                    order_totals.append(total)
                    order_statuses.append(status)
                    cp.write_row((oid, cust_id, odate, status, country, subtotal, disc, total, channel))

            print(f"[*] Seeding order_items ({n_items:,})...")
            with cur.copy(
                "COPY order_items (order_item_id, order_id, product_id, quantity, unit_price, discount_pct, line_total) FROM STDIN"
            ) as cp:
                for item_id in range(1, n_items + 1):
                    # Ensure every order gets at least one item first, then distribute randomly
                    oid = item_id if item_id <= n_orders else rng.randint(1, n_orders)
                    pid = rng.randint(1, n_products)
                    qty = rng.randint(1, 5)
                    uprice = product_prices[pid - 1]
                    dpct = rng.choice([0.0, 0.0, 5.0, 10.0, 15.0])
                    ltotal = round(qty * uprice * (1.0 - dpct / 100.0), 2)
                    cp.write_row((item_id, oid, pid, qty, uprice, dpct, ltotal))

            print(f"[*] Seeding payments ({n_payments:,})...")
            with cur.copy(
                "COPY payments (payment_id, order_id, payment_method, payment_status, amount, paid_at, transaction_ref) FROM STDIN"
            ) as cp:
                for pay_id in range(1, n_payments + 1):
                    oid = pay_id if pay_id <= n_orders else rng.randint(1, n_orders)
                    pmethod = rng.choice(PAYMENT_METHODS)
                    pstatus = rng.choice(PAYMENT_STATUSES)
                    amt = order_totals[oid - 1]
                    paid_at = order_dates[oid - 1] + timedelta(minutes=rng.randint(1, 45))
                    tref = f"TXN-{oid:06d}-{pay_id:06d}"
                    cp.write_row((pay_id, oid, pmethod, pstatus, amt, paid_at, tref))

            print(f"[*] Seeding shipments ({n_shipments:,})...")
            with cur.copy(
                "COPY shipments (shipment_id, order_id, carrier, shipment_status, shipped_at, delivered_at, shipping_cost) FROM STDIN"
            ) as cp:
                for sid in range(1, n_shipments + 1):
                    oid = sid if sid <= n_orders else rng.randint(1, n_orders)
                    carrier = rng.choice(CARRIERS)
                    sstatus = rng.choice(SHIPMENT_STATUSES)
                    shipped_at = (
                        order_dates[oid - 1] + timedelta(hours=rng.randint(4, 48))
                        if sstatus != "label_created"
                        else None
                    )
                    delivered_at = (
                        shipped_at + timedelta(days=rng.randint(1, 7))
                        if (shipped_at is not None and sstatus == "delivered")
                        else None
                    )
                    scost = round(rng.uniform(2.5, 28.0), 2)
                    cp.write_row((sid, oid, carrier, sstatus, shipped_at, delivered_at, scost))

            print(f"[*] Seeding reviews ({n_reviews:,})...")
            with cur.copy(
                "COPY reviews (review_id, product_id, customer_id, rating, is_verified, review_title, review_body, created_at) FROM STDIN"
            ) as cp:
                titles = [
                    "Solid build quality", "Great value for money", "Works as expected",
                    "Fast delivery and reliable", "Average performance", "Could be improved",
                ]
                for rid in range(1, n_reviews + 1):
                    pid = rng.randint(1, n_products)
                    cid = rng.randint(1, n_customers)
                    rating = rng.choices([1, 2, 3, 4, 5], weights=[5, 8, 17, 35, 35], k=1)[0]
                    verified = rng.random() > 0.15
                    title = rng.choice(titles)
                    body = f"Synthetic deterministic review #{rid} for product {pid} rated {rating}/5."
                    rdate = base_dt + timedelta(seconds=rng.randint(span_seconds // 4, span_seconds))
                    cp.write_row((rid, pid, cid, rating, verified, title, body, rdate))

            # Advance sequences cleanly past inserted IDs
            for tbl, pk in (
                ("categories", "category_id"),
                ("customers", "customer_id"),
                ("products", "product_id"),
                ("orders", "order_id"),
                ("order_items", "order_item_id"),
                ("payments", "payment_id"),
                ("shipments", "shipment_id"),
                ("reviews", "review_id"),
            ):
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{tbl}', '{pk}'), "
                    f"COALESCE((SELECT MAX({pk}) FROM {tbl}), 1), true)"
                )

            conn.commit()

        # Run ANALYZE in autocommit so pg_class.reltuples & planner histograms update immediately
        conn.autocommit = True
        with conn.cursor() as cur:
            print("[*] Running ANALYZE across sample tables...")
            cur.execute("ANALYZE;")

    elapsed = time.perf_counter() - t_start
    counts = {
        "categories": len(CATEGORY_DEFS),
        "customers": n_customers,
        "products": n_products,
        "orders": n_orders,
        "order_items": n_items,
        "payments": n_payments,
        "shipments": n_shipments,
        "reviews": n_reviews,
    }
    print(f"[DONE] Sample database '{cfg.database}' ready in {elapsed:.2f}s. Total rows: {sum(counts.values()):,}.")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and populate QueryTrellis PostgreSQL sample database.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--scale", type=float, default=1.0, help="Dataset scale multiplier (default: 1.0 -> ~281,525 rows)")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate sample tables before seeding")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed")
    args = parser.parse_args()

    settings = load_settings()
    cfg = settings.connection
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    if args.user:
        cfg.username = args.user
    if args.password is not None:
        cfg.password = args.password
    if args.database:
        cfg.database = args.database

    try:
        seed_sample_database(cfg, scale=args.scale, reset=args.reset, seed=args.seed)
        return 0
    except Exception as exc:
        print(f"[ERROR] {translate_pg_error(exc, cfg)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
