# QueryTrellis Data & Sample Database Methodology

This directory holds runtime operational metadata (gitignored) and documentation for the deterministic synthetic e-commerce PostgreSQL dataset.

## 1. Local SQLite Metadata Store (`data/querytrellis_meta.db`)

- Created automatically on startup (`src/db/metadata_store.py`).
- Strictly separate from the analyzed PostgreSQL database.
- Stores connection profiles (never passwords), query analysis history, EXPLAIN JSON snapshots, multi-run benchmark iterations, before/after comparison records, report history, and safety preferences.

## 2. Synthetic PostgreSQL Sample Database (`querytrellis_sample`)

- **Origin & License:** Generated 100% locally using `scripts/setup_sample_db.py` with Python's deterministic `random.Random(42)` generator (MIT License, zero external dataset downloads required).
- **Schema File:** `sql/schema.sql` (documented in `sql/schema_docs.md`).
- **Default Row Volumes (`--scale 1.0`):**
  - `categories`: 25 hierarchical categories
  - `customers`: 12,000 rows (`10,000+` requirement)
  - `products`: 2,500 rows (`2,000+` requirement)
  - `orders`: 55,000 rows (`50,000+` requirement)
  - `order_items`: 120,000 rows (`100,000+` requirement)
  - `payments`: 45,000 rows (`40,000+` requirement)
  - `shipments`: 35,000 rows (`30,000+` requirement)
  - `reviews`: 12,000 rows (`10,000+` requirement)
  - **Total:** 281,525 rows across 8 normalized relational tables.

## 3. Regeneration & Scaling Instructions

```powershell
# Default full 281,525-row dataset
.venv\Scripts\python.exe scripts\setup_sample_db.py --reset

# Faster smaller dataset (e.g., 20% scale) for constrained hardware
.venv\Scripts\python.exe scripts\setup_sample_db.py --scale 0.2 --reset
```

After bulk-loading via PostgreSQL `COPY`, `setup_sample_db.py` resets all `SERIAL` sequences and runs `ANALYZE;` so `pg_class.reltuples` and planner statistics match actual table cardinalities immediately.
