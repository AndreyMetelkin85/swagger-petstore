CREATE TABLE catalog_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('product', 'pet')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (kind, name)
);

CREATE TABLE media (
    id UUID PRIMARY KEY,
    mime_type VARCHAR(30) NOT NULL,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    size_bytes BIGINT NOT NULL,
    source_type VARCHAR(10) NOT NULL CHECK (source_type IN ('OWN', 'SUPPLIER', 'DEMO')),
    source_note VARCHAR(1000) NOT NULL DEFAULT '',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(150) NOT NULL,
    description VARCHAR(5000) NOT NULL DEFAULT '',
    category_id UUID REFERENCES catalog_categories(id) ON DELETE RESTRICT,
    brand VARCHAR(100) NOT NULL DEFAULT '',
    product_type VARCHAR(20) NOT NULL DEFAULT 'OTHER'
        CHECK (product_type IN ('FEED','TREAT','TOY','ACCESSORY','HYGIENE','OTHER')),
    animal_types JSONB NOT NULL DEFAULT '[]',
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
    feed_form VARCHAR(10) NOT NULL DEFAULT '',
    life_stages JSONB NOT NULL DEFAULT '[]',
    net_weight_grams INTEGER,
    ingredients VARCHAR(5000) NOT NULL DEFAULT '',
    publication_status VARCHAR(10) NOT NULL DEFAULT 'DRAFT'
        CHECK (publication_status IN ('DRAFT','PUBLISHED','ARCHIVED')),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved <= stock),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_products_sku_unique ON products (LOWER(sku));
CREATE INDEX idx_products_catalog ON products (publication_status, category_id);

ALTER TABLE pets ADD COLUMN description VARCHAR(5000) NOT NULL DEFAULT '';
ALTER TABLE pets ADD COLUMN animal_type VARCHAR(10) NOT NULL DEFAULT 'other';
ALTER TABLE pets ADD COLUMN breed VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE pets ADD COLUMN sex VARCHAR(10) NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE pets ADD COLUMN birth_date DATE;
ALTER TABLE pets ADD COLUMN category_id UUID REFERENCES catalog_categories(id) ON DELETE RESTRICT;
-- Legacy cards remain visible; the new administrator endpoint creates DRAFT explicitly.
ALTER TABLE pets ADD COLUMN publication_status VARCHAR(10) NOT NULL DEFAULT 'PUBLISHED'
    CHECK (publication_status IN ('DRAFT','PUBLISHED','ARCHIVED'));

CREATE TABLE catalog_images (
    media_id UUID NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
    product_id UUID REFERENCES products(id) ON DELETE RESTRICT,
    pet_id UUID REFERENCES pets(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK (position >= 0 AND position < 20),
    alt VARCHAR(300) NOT NULL DEFAULT '',
    is_cover BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (num_nonnulls(product_id, pet_id) = 1)
);
CREATE UNIQUE INDEX idx_product_image_unique ON catalog_images (product_id, media_id) WHERE product_id IS NOT NULL;
CREATE UNIQUE INDEX idx_pet_image_unique ON catalog_images (pet_id, media_id) WHERE pet_id IS NOT NULL;
CREATE UNIQUE INDEX idx_product_cover_unique ON catalog_images (product_id) WHERE is_cover AND product_id IS NOT NULL;
CREATE UNIQUE INDEX idx_pet_cover_unique ON catalog_images (pet_id) WHERE is_cover AND pet_id IS NOT NULL;

CREATE TABLE stock_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    delta INTEGER NOT NULL,
    reason VARCHAR(300) NOT NULL,
    before_stock INTEGER NOT NULL,
    after_stock INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
