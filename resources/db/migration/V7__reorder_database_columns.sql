-- PostgreSQL executes this Flyway migration in a single transaction. Temporary
-- tables are populated and verified before the original tables are replaced.

LOCK TABLE payments, store_orders, pets, users IN ACCESS EXCLUSIVE MODE;

CREATE TABLE users_v7 (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    username VARCHAR(30) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(254),
    password VARCHAR(100) NOT NULL,
    role VARCHAR(10) NOT NULL DEFAULT 'USER',
    user_status account_status NOT NULL DEFAULT 'PENDING',
    phone VARCHAR(30),
    address_city VARCHAR(100),
    address_street VARCHAR(150),
    address_house VARCHAR(30),
    address_apartment VARCHAR(30),
    address_postal_code CHAR(6),
    confirmation_code_hash CHAR(64),
    confirmation_expires_at TIMESTAMPTZ,
    reset_code_hash CHAR(64),
    reset_expires_at TIMESTAMPTZ,
    reset_used_at TIMESTAMPTZ,
    token_version INTEGER NOT NULL DEFAULT 0,
    confirmed_at TIMESTAMPTZ
);

CREATE TABLE pets_v7 (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    status pet_status NOT NULL,
    category_json TEXT NOT NULL DEFAULT 'null',
    photo_urls_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    price NUMERIC(12, 2) NOT NULL DEFAULT 10000.00,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE store_orders_v7 (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL,
    pet_id UUID NOT NULL,
    quantity INTEGER NOT NULL,
    status order_status NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL DEFAULT 10000.00,
    total_amount NUMERIC(14, 2) NOT NULL DEFAULT 10000.00,
    currency CHAR(3) NOT NULL DEFAULT 'RUB',
    delivery_details JSONB,
    payment_status order_payment_status NOT NULL DEFAULT 'NOT_REQUIRED',
    payment_expires_at TIMESTAMPTZ,
    ship_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    complete BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payments_v7 (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL,
    status payment_attempt_status NOT NULL,
    idempotency_key UUID NOT NULL,
    request_hash CHAR(64) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'RUB',
    card_brand VARCHAR(20) NOT NULL,
    card_last4 CHAR(4) NOT NULL,
    failure_code VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users_v7 (
    id, username, first_name, last_name, email, password, role, user_status, phone,
    address_city, address_street, address_house, address_apartment, address_postal_code,
    confirmation_code_hash, confirmation_expires_at, reset_code_hash, reset_expires_at,
    reset_used_at, token_version, confirmed_at
)
SELECT
    id, username, first_name, last_name, email, password, role, user_status, phone,
    address_city, address_street, address_house, address_apartment, address_postal_code,
    confirmation_code_hash, confirmation_expires_at, reset_code_hash, reset_expires_at,
    reset_used_at, token_version, confirmed_at
FROM users;

INSERT INTO pets_v7 (
    id, name, status, category_json, photo_urls_json, tags_json, price, version
)
SELECT
    id, name, status, category_json, photo_urls_json, tags_json, price, version
FROM pets;

INSERT INTO store_orders_v7 (
    id, owner_user_id, pet_id, quantity, status, unit_price, total_amount, currency,
    delivery_details, payment_status, payment_expires_at, ship_date, complete, created_at
)
SELECT
    id, owner_user_id, pet_id, quantity, status, unit_price, total_amount, currency,
    delivery_details, payment_status, payment_expires_at, ship_date, complete, created_at
FROM store_orders;

INSERT INTO payments_v7 (
    id, order_id, status, idempotency_key, request_hash, amount, currency, card_brand,
    card_last4, failure_code, created_at, updated_at
)
SELECT
    id, order_id, status, idempotency_key, request_hash, amount, currency, card_brand,
    card_last4, failure_code, created_at, updated_at
FROM payments;

DO $$
BEGIN
    IF (SELECT COUNT(*) FROM users) <> (SELECT COUNT(*) FROM users_v7)
       OR (SELECT COUNT(*) FROM pets) <> (SELECT COUNT(*) FROM pets_v7)
       OR (SELECT COUNT(*) FROM store_orders) <> (SELECT COUNT(*) FROM store_orders_v7)
       OR (SELECT COUNT(*) FROM payments) <> (SELECT COUNT(*) FROM payments_v7) THEN
        RAISE EXCEPTION 'V7 data copy row-count verification failed';
    END IF;
END
$$;

DROP TABLE payments;
DROP TABLE store_orders;
DROP TABLE pets;
DROP TABLE users;

ALTER TABLE users_v7 RENAME TO users;
ALTER TABLE pets_v7 RENAME TO pets;
ALTER TABLE store_orders_v7 RENAME TO store_orders;
ALTER TABLE payments_v7 RENAME TO payments;

ALTER TABLE users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id),
    ADD CONSTRAINT users_username_key UNIQUE (username),
    ADD CONSTRAINT users_role_check CHECK (role IN ('USER', 'ADMIN')),
    ADD CONSTRAINT users_address_complete CHECK (
        (address_city IS NULL AND address_street IS NULL AND address_house IS NULL
            AND address_apartment IS NULL AND address_postal_code IS NULL)
        OR
        (address_city IS NOT NULL AND address_street IS NOT NULL AND address_house IS NOT NULL
            AND address_postal_code IS NOT NULL
            AND address_postal_code ~ '^[0-9]{6}$')
    );

CREATE UNIQUE INDEX uq_users_email_lower ON users (LOWER(email));
CREATE INDEX idx_users_status ON users (user_status);

ALTER TABLE pets
    ADD CONSTRAINT pets_pkey PRIMARY KEY (id),
    ADD CONSTRAINT pets_price_positive CHECK (price >= 0.01),
    ADD CONSTRAINT pets_price_two_decimals CHECK (price = ROUND(price, 2)),
    ADD CONSTRAINT pets_version_non_negative CHECK (version >= 0);

CREATE INDEX idx_pets_status ON pets (status);

ALTER TABLE store_orders
    ADD CONSTRAINT store_orders_pkey PRIMARY KEY (id),
    ADD CONSTRAINT store_orders_quantity_check CHECK (quantity >= 1),
    ADD CONSTRAINT store_orders_price_positive CHECK (unit_price >= 0.01),
    ADD CONSTRAINT store_orders_total_positive CHECK (total_amount >= 0.01),
    ADD CONSTRAINT store_orders_currency_rub CHECK (currency = 'RUB'),
    ADD CONSTRAINT fk_store_orders_owner_user
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_store_orders_pet
        FOREIGN KEY (pet_id) REFERENCES pets(id) ON DELETE RESTRICT NOT VALID;

CREATE INDEX idx_store_orders_owner_user ON store_orders (owner_user_id);
CREATE INDEX idx_store_orders_pet ON store_orders (pet_id);
CREATE INDEX idx_store_orders_pet_status ON store_orders (pet_id, status);
CREATE UNIQUE INDEX uq_store_orders_one_active_per_pet
    ON store_orders (pet_id)
    WHERE status IN ('placed', 'approved', 'shipped');
CREATE INDEX idx_store_orders_payment_expiry
    ON store_orders (payment_expires_at)
    WHERE status = 'placed' AND payment_status = 'UNPAID';

ALTER TABLE payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id),
    ADD CONSTRAINT uq_payments_idempotency_key UNIQUE (idempotency_key),
    ADD CONSTRAINT payments_amount_check CHECK (amount >= 0.01),
    ADD CONSTRAINT payments_currency_check CHECK (currency = 'RUB'),
    ADD CONSTRAINT payments_card_last4_check CHECK (card_last4 ~ '^[0-9]{4}$'),
    ADD CONSTRAINT payments_order_id_fkey
        FOREIGN KEY (order_id) REFERENCES store_orders(id) ON DELETE RESTRICT;

CREATE INDEX idx_payments_order_created ON payments (order_id, created_at, id);
CREATE UNIQUE INDEX uq_payments_one_success_per_order
    ON payments (order_id)
    WHERE status IN ('SUCCEEDED', 'REFUNDED');
