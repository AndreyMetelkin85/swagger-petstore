-- Extend the existing parent and payment relation; no legacy row is rewritten or removed.
ALTER TABLE store_orders ALTER COLUMN pet_id DROP NOT NULL;
ALTER TABLE store_orders ADD COLUMN order_kind VARCHAR(10) NOT NULL DEFAULT 'LEGACY'
    CHECK (order_kind IN ('LEGACY','MIXED'));
ALTER TABLE store_orders ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE store_orders ADD COLUMN cart_version INTEGER;

CREATE TABLE carts (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE cart_lines (
    user_id UUID NOT NULL REFERENCES carts(user_id) ON DELETE RESTRICT,
    item_type VARCHAR(10) NOT NULL CHECK (item_type IN ('product','pet')),
    item_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0 AND quantity <= 1000000),
    name_snapshot VARCHAR(150) NOT NULL DEFAULT '',
    price_snapshot NUMERIC(12,2),
    PRIMARY KEY (user_id, item_type, item_id),
    CHECK (item_type <> 'pet' OR quantity = 1)
);
CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES store_orders(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    item_type VARCHAR(10) NOT NULL CHECK (item_type IN ('product','pet')),
    item_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    name VARCHAR(150) NOT NULL,
    sku VARCHAR(64) NOT NULL DEFAULT '',
    unit_price NUMERIC(12,2) NOT NULL,
    cover_id UUID REFERENCES media(id) ON DELETE RESTRICT,
    snapshot JSONB NOT NULL,
    allocation VARCHAR(10) NOT NULL DEFAULT 'NONE'
        CHECK (allocation IN ('NONE','RESERVED','RELEASED','CONSUMED')),
    PRIMARY KEY (order_id, position),
    UNIQUE (order_id, item_type, item_id),
    CHECK (item_type <> 'pet' OR quantity = 1)
);
CREATE INDEX idx_order_lines_inventory ON order_lines (item_type, item_id, allocation);

CREATE TABLE api_idempotency (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    operation VARCHAR(150) NOT NULL,
    key UUID NOT NULL,
    request_hash CHAR(64) NOT NULL,
    result JSONB NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, operation, key)
);
