-- Adds draft orders without rewriting or deleting existing business data.
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'draft' BEFORE 'placed';
ALTER TYPE order_payment_status ADD VALUE IF NOT EXISTS 'NOT_STARTED' BEFORE 'NOT_REQUIRED';

ALTER TABLE store_orders ALTER COLUMN unit_price DROP NOT NULL;
ALTER TABLE store_orders ALTER COLUMN unit_price DROP DEFAULT;
ALTER TABLE store_orders ALTER COLUMN total_amount DROP NOT NULL;
ALTER TABLE store_orders ALTER COLUMN total_amount DROP DEFAULT;
ALTER TABLE store_orders ALTER COLUMN ship_date DROP DEFAULT;

CREATE TABLE protected_user_accounts (
    user_id UUID PRIMARY KEY,
    reason VARCHAR(30) NOT NULL,
    CONSTRAINT fk_protected_user_accounts_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

INSERT INTO protected_user_accounts (user_id, reason)
SELECT id, 'DEMO_USER'
FROM users
WHERE username = 'user1' OR LOWER(email) = 'test@example.com'
ON CONFLICT (user_id) DO NOTHING;
