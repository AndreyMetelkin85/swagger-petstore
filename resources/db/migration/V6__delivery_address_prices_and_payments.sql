-- Extend the existing schema without removing users, pets, orders, or Docker volume data.

ALTER TABLE users
    ADD COLUMN address_city VARCHAR(100),
    ADD COLUMN address_street VARCHAR(150),
    ADD COLUMN address_house VARCHAR(30),
    ADD COLUMN address_apartment VARCHAR(30),
    ADD COLUMN address_postal_code CHAR(6);

ALTER TABLE users
    ADD CONSTRAINT users_address_complete CHECK (
        (address_city IS NULL AND address_street IS NULL AND address_house IS NULL
            AND address_apartment IS NULL AND address_postal_code IS NULL)
        OR
        (address_city IS NOT NULL AND address_street IS NOT NULL AND address_house IS NOT NULL
            AND address_postal_code IS NOT NULL
            AND address_postal_code ~ '^[0-9]{6}$')
    );

ALTER TABLE pets
    ADD COLUMN price NUMERIC(12, 2) NOT NULL DEFAULT 10000.00;

ALTER TABLE pets
    ADD CONSTRAINT pets_price_positive CHECK (price >= 0.01),
    ADD CONSTRAINT pets_price_two_decimals CHECK (price = ROUND(price, 2));

-- Replace the enum so the new terminal value can be used by later statements
-- within the same Flyway transaction on every supported PostgreSQL version.
DROP INDEX IF EXISTS uq_store_orders_one_active_per_pet;
CREATE TYPE order_status_v6 AS ENUM
    ('placed', 'approved', 'shipped', 'delivered', 'cancelled', 'expired');
ALTER TABLE store_orders
    ALTER COLUMN status TYPE order_status_v6 USING status::text::order_status_v6;
DROP TYPE order_status;
ALTER TYPE order_status_v6 RENAME TO order_status;

ALTER TABLE store_orders ADD COLUMN owner_user_id UUID;
UPDATE store_orders AS orders
SET owner_user_id = users.id
FROM users
WHERE users.username = orders.owner_username;
ALTER TABLE store_orders ALTER COLUMN owner_user_id SET NOT NULL;
ALTER TABLE store_orders DROP CONSTRAINT IF EXISTS store_orders_owner_username_fkey;
DROP INDEX IF EXISTS idx_store_orders_owner;
ALTER TABLE store_orders DROP COLUMN owner_username;
ALTER TABLE store_orders
    ADD CONSTRAINT fk_store_orders_owner_user
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT;
CREATE INDEX idx_store_orders_owner_user ON store_orders(owner_user_id);

CREATE TYPE order_payment_status AS ENUM
    ('NOT_REQUIRED', 'UNPAID', 'PAID', 'REFUNDED', 'EXPIRED');

ALTER TABLE store_orders
    ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN unit_price NUMERIC(12, 2) NOT NULL DEFAULT 10000.00,
    ADD COLUMN total_amount NUMERIC(14, 2) NOT NULL DEFAULT 10000.00,
    ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'RUB',
    ADD COLUMN delivery_details JSONB,
    ADD COLUMN payment_status order_payment_status NOT NULL DEFAULT 'NOT_REQUIRED',
    ADD COLUMN payment_expires_at TIMESTAMPTZ;

UPDATE store_orders AS orders
SET created_at = COALESCE(orders.ship_date, orders.created_at),
    unit_price = COALESCE(pets.price, 10000.00),
    total_amount = COALESCE(pets.price, 10000.00) * orders.quantity
FROM pets
WHERE pets.id = orders.pet_id;

-- Covers preserved legacy orphan orders which intentionally have no matching pet row.
UPDATE store_orders
SET total_amount = unit_price * quantity
WHERE total_amount <> unit_price * quantity;

ALTER TABLE store_orders
    ADD CONSTRAINT store_orders_price_positive CHECK (unit_price >= 0.01),
    ADD CONSTRAINT store_orders_total_positive CHECK (total_amount >= 0.01),
    ADD CONSTRAINT store_orders_currency_rub CHECK (currency = 'RUB');

CREATE UNIQUE INDEX uq_store_orders_one_active_per_pet
    ON store_orders (pet_id)
    WHERE status IN ('placed', 'approved', 'shipped');
CREATE INDEX idx_store_orders_payment_expiry
    ON store_orders (payment_expires_at)
    WHERE status = 'placed' AND payment_status = 'UNPAID';

CREATE TYPE payment_attempt_status AS ENUM ('SUCCEEDED', 'DECLINED', 'REFUNDED');

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES store_orders(id) ON DELETE RESTRICT,
    idempotency_key UUID NOT NULL,
    request_hash CHAR(64) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0.01),
    currency CHAR(3) NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
    status payment_attempt_status NOT NULL,
    card_brand VARCHAR(20) NOT NULL,
    card_last4 CHAR(4) NOT NULL CHECK (card_last4 ~ '^[0-9]{4}$'),
    failure_code VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_payments_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX idx_payments_order_created ON payments(order_id, created_at, id);
CREATE UNIQUE INDEX uq_payments_one_success_per_order
    ON payments(order_id)
    WHERE status IN ('SUCCEEDED', 'REFUNDED');
