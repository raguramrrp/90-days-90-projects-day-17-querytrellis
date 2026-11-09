-- =============================================================================
-- QueryTrellis Sample E-Commerce Schema (PostgreSQL 14+)
-- =============================================================================
-- Intentionally mirrors real-world OLTP/analytical PostgreSQL schemas:
--   - Primary keys and unique constraints on entity identifiers
--   - Explicit foreign key relationships and domain CHECK constraints
--   - Selective initial indexes (products.category_id, customers.email) while
--     leaving several high-traffic FK/filter/sort columns unindexed initially
--     so QueryTrellis can demonstrate real EXPLAIN bottlenecks, non-sargable
--     predicates, and measurable index recommendations.
-- =============================================================================

CREATE TABLE IF NOT EXISTS categories (
    category_id        SERIAL PRIMARY KEY,
    category_name      VARCHAR(100) NOT NULL,
    parent_category_id INTEGER REFERENCES categories(category_id) ON DELETE SET NULL,
    slug               VARCHAR(120) NOT NULL UNIQUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id        SERIAL PRIMARY KEY,
    first_name         VARCHAR(80) NOT NULL,
    last_name          VARCHAR(80) NOT NULL,
    email              VARCHAR(160) NOT NULL UNIQUE,
    country            VARCHAR(60) NOT NULL,
    city               VARCHAR(80) NOT NULL,
    segment            VARCHAR(30) NOT NULL CHECK (segment IN ('consumer', 'smb', 'enterprise', 'vip')),
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    product_id         SERIAL PRIMARY KEY,
    category_id        INTEGER NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    sku                VARCHAR(40) NOT NULL UNIQUE,
    product_name       VARCHAR(180) NOT NULL,
    brand              VARCHAR(80) NOT NULL,
    unit_price         NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    cost_price         NUMERIC(10, 2) NOT NULL CHECK (cost_price >= 0),
    stock_quantity     INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    is_discontinued    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Pre-existing index to demonstrate "indexed vs non-indexed column" filtering
CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);

CREATE TABLE IF NOT EXISTS orders (
    order_id           SERIAL PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    order_date         TIMESTAMPTZ NOT NULL,
    status             VARCHAR(24) NOT NULL CHECK (
                           status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled', 'returned')
                       ),
    shipping_country   VARCHAR(60) NOT NULL,
    subtotal_amount    NUMERIC(12, 2) NOT NULL CHECK (subtotal_amount >= 0),
    discount_amount    NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    total_amount       NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    sales_channel      VARCHAR(24) NOT NULL CHECK (sales_channel IN ('web', 'mobile', 'api', 'marketplace'))
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id      SERIAL PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id         INTEGER NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    unit_price         NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    discount_pct       NUMERIC(5, 2) NOT NULL DEFAULT 0 CHECK (discount_pct >= 0 AND discount_pct <= 100),
    line_total         NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id         SERIAL PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    payment_method     VARCHAR(30) NOT NULL CHECK (
                           payment_method IN ('card', 'upi', 'netbanking', 'wallet', 'cod')
                       ),
    payment_status     VARCHAR(24) NOT NULL CHECK (
                           payment_status IN ('authorized', 'captured', 'failed', 'refunded')
                       ),
    amount             NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    paid_at            TIMESTAMPTZ NOT NULL,
    transaction_ref    VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id        SERIAL PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    carrier            VARCHAR(40) NOT NULL CHECK (
                           carrier IN ('BlueDart', 'Delhivery', 'DHL', 'FedEx', 'IndiaPost')
                       ),
    shipment_status    VARCHAR(24) NOT NULL CHECK (
                           shipment_status IN ('label_created', 'in_transit', 'out_for_delivery', 'delivered', 'delayed')
                       ),
    shipped_at         TIMESTAMPTZ,
    delivered_at       TIMESTAMPTZ,
    shipping_cost      NUMERIC(10, 2) NOT NULL CHECK (shipping_cost >= 0)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id          SERIAL PRIMARY KEY,
    product_id         INTEGER NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    rating             SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    is_verified        BOOLEAN NOT NULL DEFAULT TRUE,
    review_title       VARCHAR(160) NOT NULL,
    review_body        TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
