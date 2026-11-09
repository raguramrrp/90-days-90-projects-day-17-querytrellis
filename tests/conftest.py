"""Shared pytest fixtures for QueryTrellis unit and integration tests."""
from __future__ import annotations

import pytest

from src.db.connection_manager import (
    ColumnMetadata,
    DatabaseCatalog,
    IndexMetadata,
    TableMetadata,
)
from src.db.metadata_store import MetadataStore


@pytest.fixture()
def sample_catalog() -> DatabaseCatalog:
    """Realistic offline DatabaseCatalog mirroring the QueryTrellis e-commerce schema."""
    categories = TableMetadata(
        schema_name="public",
        table_name="categories",
        table_type="BASE TABLE",
        estimated_rows=25,
        total_size_bytes=16384,
        table_size_bytes=8192,
        index_size_bytes=8192,
        columns=[
            ColumnMetadata("public", "categories", "category_id", "integer", False, 1),
            ColumnMetadata("public", "categories", "category_name", "character varying(100)", False, 2),
        ],
        indexes=[
            IndexMetadata(
                "public", "categories", "categories_pkey", "btree", ["category_id"], [], True, True, None,
                "CREATE UNIQUE INDEX categories_pkey ON public.categories USING btree (category_id)"
            )
        ],
    )

    customers = TableMetadata(
        schema_name="public",
        table_name="customers",
        table_type="BASE TABLE",
        estimated_rows=12000,
        total_size_bytes=2097152,
        table_size_bytes=1572864,
        index_size_bytes=524288,
        columns=[
            ColumnMetadata("public", "customers", "customer_id", "integer", False, 1),
            ColumnMetadata("public", "customers", "email", "character varying(160)", False, 2),
            ColumnMetadata("public", "customers", "country", "character varying(60)", False, 3),
            ColumnMetadata("public", "customers", "segment", "character varying(30)", False, 4),
        ],
        indexes=[
            IndexMetadata(
                "public", "customers", "customers_pkey", "btree", ["customer_id"], [], True, True, None,
                "CREATE UNIQUE INDEX customers_pkey ON public.customers USING btree (customer_id)"
            ),
            IndexMetadata(
                "public", "customers", "customers_email_key", "btree", ["email"], [], True, False, None,
                "CREATE UNIQUE INDEX customers_email_key ON public.customers USING btree (email)"
            ),
        ],
    )

    products = TableMetadata(
        schema_name="public",
        table_name="products",
        table_type="BASE TABLE",
        estimated_rows=2500,
        total_size_bytes=524288,
        table_size_bytes=393216,
        index_size_bytes=131072,
        columns=[
            ColumnMetadata("public", "products", "product_id", "integer", False, 1),
            ColumnMetadata("public", "products", "category_id", "integer", False, 2),
            ColumnMetadata("public", "products", "brand", "character varying(80)", False, 3),
            ColumnMetadata("public", "products", "unit_price", "numeric(10,2)", False, 4),
        ],
        indexes=[
            IndexMetadata(
                "public", "products", "products_pkey", "btree", ["product_id"], [], True, True, None,
                "CREATE UNIQUE INDEX products_pkey ON public.products USING btree (product_id)"
            ),
            IndexMetadata(
                "public", "products", "idx_products_category_id", "btree", ["category_id"], [], False, False, None,
                "CREATE INDEX idx_products_category_id ON public.products USING btree (category_id)"
            ),
        ],
    )

    orders = TableMetadata(
        schema_name="public",
        table_name="orders",
        table_type="BASE TABLE",
        estimated_rows=55000,
        total_size_bytes=8388608,
        table_size_bytes=6291456,
        index_size_bytes=2097152,
        columns=[
            ColumnMetadata("public", "orders", "order_id", "integer", False, 1),
            ColumnMetadata("public", "orders", "customer_id", "integer", False, 2),
            ColumnMetadata("public", "orders", "order_date", "timestamp with time zone", False, 3),
            ColumnMetadata("public", "orders", "status", "character varying(24)", False, 4),
            ColumnMetadata("public", "orders", "total_amount", "numeric(12,2)", False, 5),
        ],
        indexes=[
            IndexMetadata(
                "public", "orders", "orders_pkey", "btree", ["order_id"], [], True, True, None,
                "CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (order_id)"
            ),
        ],
    )

    return DatabaseCatalog(
        database_name="querytrellis_sample",
        server_version="PostgreSQL 18.6",
        server_version_num=180006,
        schemas=["public"],
        tables=[categories, customers, products, orders],
    )


@pytest.fixture()
def temp_store(tmp_path) -> MetadataStore:
    """Isolated temporary SQLite metadata store."""
    return MetadataStore(tmp_path / "test_meta.db")
