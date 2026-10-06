CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users ADD COLUMN id_uuid UUID DEFAULT gen_random_uuid();
ALTER TABLE pets ADD COLUMN id_uuid UUID DEFAULT gen_random_uuid();
ALTER TABLE store_orders ADD COLUMN id_uuid UUID DEFAULT gen_random_uuid();
ALTER TABLE store_orders ADD COLUMN pet_id_uuid UUID;

UPDATE users SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL;
UPDATE pets SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL;
UPDATE store_orders SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL;
UPDATE store_orders AS orders
SET pet_id_uuid = pets.id_uuid
FROM pets
WHERE orders.pet_id = pets.id;

-- Older versions allowed an order to reference a missing pet. Preserve such
-- records with a valid UUID instead of deleting user data during migration.
UPDATE store_orders SET pet_id_uuid = gen_random_uuid() WHERE pet_id_uuid IS NULL;

UPDATE pets
SET category_json = CASE
    WHEN category_json::jsonb = 'null'::jsonb THEN 'null'
    ELSE jsonb_set(
        category_json::jsonb,
        '{id}',
        to_jsonb(gen_random_uuid()::text),
        true
    )::text
END;

UPDATE pets AS pet
SET tags_json = COALESCE((
    SELECT jsonb_agg(
        jsonb_set(tag.value, '{id}', to_jsonb(gen_random_uuid()::text), true)
    )
    FROM jsonb_array_elements(pet.tags_json::jsonb) AS tag(value)
), '[]'::jsonb)::text;

ALTER TABLE users ALTER COLUMN id_uuid SET NOT NULL;
ALTER TABLE pets ALTER COLUMN id_uuid SET NOT NULL;
ALTER TABLE store_orders ALTER COLUMN id_uuid SET NOT NULL;
ALTER TABLE store_orders ALTER COLUMN pet_id_uuid SET NOT NULL;

ALTER TABLE users DROP CONSTRAINT users_pkey;
ALTER TABLE pets DROP CONSTRAINT pets_pkey;
ALTER TABLE store_orders DROP CONSTRAINT store_orders_pkey;

ALTER TABLE users DROP COLUMN id;
ALTER TABLE pets DROP COLUMN id;
ALTER TABLE store_orders DROP COLUMN id;
ALTER TABLE store_orders DROP COLUMN pet_id;

ALTER TABLE users RENAME COLUMN id_uuid TO id;
ALTER TABLE pets RENAME COLUMN id_uuid TO id;
ALTER TABLE store_orders RENAME COLUMN id_uuid TO id;
ALTER TABLE store_orders RENAME COLUMN pet_id_uuid TO pet_id;

ALTER TABLE users ADD PRIMARY KEY (id);
ALTER TABLE pets ADD PRIMARY KEY (id);
ALTER TABLE store_orders ADD PRIMARY KEY (id);
CREATE INDEX IF NOT EXISTS idx_store_orders_pet ON store_orders(pet_id);
