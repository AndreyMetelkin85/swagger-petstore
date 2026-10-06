-- Preserve order history when account-management code changes in the future.
ALTER TABLE store_orders
    DROP CONSTRAINT IF EXISTS store_orders_owner_username_fkey;

ALTER TABLE store_orders
    ADD CONSTRAINT store_orders_owner_username_fkey
    FOREIGN KEY (owner_username) REFERENCES users(username)
    ON UPDATE CASCADE ON DELETE RESTRICT;

-- Legacy versions allowed several active orders for the same individual pet.
-- Keep the earliest active order and close the others without deleting history.
WITH ranked_active_orders AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY pet_id ORDER BY id) AS position
    FROM store_orders
    WHERE status IN ('placed', 'approved', 'shipped')
)
UPDATE store_orders AS orders
SET status = 'cancelled',
    complete = TRUE
FROM ranked_active_orders AS ranked
WHERE orders.id = ranked.id
  AND ranked.position > 1;

CREATE UNIQUE INDEX uq_store_orders_one_active_per_pet
    ON store_orders (pet_id)
    WHERE status IN ('placed', 'approved', 'shipped');

-- Reconcile catalog state after closing duplicate active orders.
UPDATE pets AS pet
SET status = CASE
    WHEN EXISTS (
        SELECT 1 FROM store_orders AS orders
        WHERE orders.pet_id = pet.id
          AND orders.status IN ('placed', 'approved', 'shipped')
    ) THEN 'reserved'::pet_status
    WHEN EXISTS (
        SELECT 1 FROM store_orders AS orders
        WHERE orders.pet_id = pet.id
          AND orders.status = 'delivered'
    ) THEN 'sold'::pet_status
    ELSE pet.status
END;

-- Optimistic locking prevents two administrators from silently overwriting
-- each other's pet edits. Order-driven status changes increment this version too.
ALTER TABLE pets
    ADD COLUMN version INTEGER NOT NULL DEFAULT 0;

ALTER TABLE pets
    ADD CONSTRAINT pets_version_non_negative CHECK (version >= 0);
