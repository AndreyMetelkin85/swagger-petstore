CREATE TYPE pet_status AS ENUM ('available', 'pending', 'reserved', 'sold');
CREATE TYPE order_status AS ENUM ('placed', 'approved', 'shipped', 'delivered', 'cancelled');

ALTER TABLE pets DROP CONSTRAINT IF EXISTS pets_status_check;
ALTER TABLE pets
    ALTER COLUMN status TYPE pet_status USING status::pet_status;

ALTER TABLE store_orders DROP CONSTRAINT IF EXISTS store_orders_status_check;
ALTER TABLE store_orders
    ALTER COLUMN status TYPE order_status USING status::order_status;
ALTER TABLE store_orders ALTER COLUMN ship_date DROP NOT NULL;

-- Preserve all legacy rows. Existing orphan orders remain readable, while the
-- NOT VALID foreign key protects every new write without deleting old data.
ALTER TABLE store_orders
    ADD CONSTRAINT fk_store_orders_pet
    FOREIGN KEY (pet_id) REFERENCES pets(id) ON DELETE RESTRICT NOT VALID;

CREATE INDEX IF NOT EXISTS idx_store_orders_pet_status
    ON store_orders (pet_id, status);

UPDATE store_orders SET complete = TRUE WHERE status = 'delivered';

UPDATE pets AS pet
SET status = 'sold'
WHERE EXISTS (
    SELECT 1
    FROM store_orders AS orders
    WHERE orders.pet_id = pet.id
      AND orders.status = 'delivered'
)
AND NOT EXISTS (
    SELECT 1
    FROM store_orders AS orders
    WHERE orders.pet_id = pet.id
      AND orders.status IN ('placed', 'approved', 'shipped')
);

UPDATE pets AS pet
SET status = 'reserved'
WHERE EXISTS (
    SELECT 1
    FROM store_orders AS orders
    WHERE orders.pet_id = pet.id
      AND orders.status IN ('placed', 'approved', 'shipped')
);
