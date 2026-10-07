-- Keep existing records and historical migration checksums unchanged.
ALTER TABLE products ALTER COLUMN sku DROP NOT NULL;
ALTER TABLE products ALTER COLUMN product_type DROP NOT NULL;
ALTER TABLE products ALTER COLUMN product_type DROP DEFAULT;
ALTER TABLE products ALTER COLUMN price DROP NOT NULL;
ALTER TABLE products ADD CONSTRAINT products_published_values CHECK
    (publication_status <> 'PUBLISHED' OR (sku IS NOT NULL AND product_type IS NOT NULL AND price IS NOT NULL));
ALTER TABLE pets ALTER COLUMN price DROP NOT NULL;
ALTER TABLE pets ALTER COLUMN price DROP DEFAULT;
ALTER TABLE pets ALTER COLUMN animal_type DROP NOT NULL;
ALTER TABLE pets ALTER COLUMN animal_type DROP DEFAULT;
ALTER TABLE pets ADD CONSTRAINT pets_published_price CHECK (publication_status <> 'PUBLISHED' OR price IS NOT NULL);

-- Migrate only previously paid, undelivered product reserves to payment-time debits.
WITH debits AS (
    SELECT l.item_id, SUM(l.quantity)::integer AS quantity
    FROM order_lines l JOIN store_orders o ON o.id=l.order_id
    WHERE o.order_kind='MIXED' AND o.payment_status='PAID' AND o.status IN ('placed','approved','shipped')
      AND l.item_type='product' AND l.allocation='RESERVED' GROUP BY l.item_id
)
UPDATE products p SET stock=p.stock-d.quantity, reserved=p.reserved-d.quantity, version=p.version+1
FROM debits d WHERE p.id=d.item_id;
UPDATE order_lines l SET allocation='CONSUMED' FROM store_orders o
WHERE l.order_id=o.id AND o.order_kind='MIXED' AND o.payment_status='PAID' AND o.status IN ('placed','approved','shipped')
  AND l.item_type='product' AND l.allocation='RESERVED';
CREATE INDEX idx_media_cleanup ON media (created_at, id) WHERE NOT deleted;
ALTER TABLE media ADD COLUMN files_removed BOOLEAN NOT NULL DEFAULT FALSE;
