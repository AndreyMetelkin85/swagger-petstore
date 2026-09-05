CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(30) NOT NULL UNIQUE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(254),
    password VARCHAR(100) NOT NULL,
    phone VARCHAR(30),
    user_status INTEGER NOT NULL DEFAULT 1,
    role VARCHAR(10) NOT NULL DEFAULT 'USER' CHECK (role IN ('USER', 'ADMIN'))
);

CREATE TABLE IF NOT EXISTS pets (
    id BIGSERIAL PRIMARY KEY,
    category_json TEXT NOT NULL DEFAULT 'null',
    name VARCHAR(100) NOT NULL,
    photo_urls_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(10) NOT NULL CHECK (status IN ('available', 'pending', 'sold'))
);

CREATE TABLE IF NOT EXISTS store_orders (
    id BIGSERIAL PRIMARY KEY,
    pet_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 1),
    ship_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(12) NOT NULL CHECK (status IN ('placed', 'approved', 'delivered')),
    complete BOOLEAN NOT NULL DEFAULT FALSE,
    owner_username VARCHAR(30) NOT NULL REFERENCES users(username)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pets_status ON pets(status);
CREATE INDEX IF NOT EXISTS idx_store_orders_owner ON store_orders(owner_username);

INSERT INTO users
    (id, username, first_name, last_name, email, password, phone, user_status, role)
VALUES
    (1, 'admin', 'Local', 'Admin', 'admin@example.com', 'admin123', '+1-555-0100', 1, 'ADMIN'),
    (2, 'user1', 'Test', 'User', 'test@example.com', 'password123', '+1-555-0101', 1, 'USER')
ON CONFLICT (username) DO NOTHING;

INSERT INTO pets
    (id, category_json, name, photo_urls_json, tags_json, status)
VALUES
    (1, '{"id":2,"name":"Cats"}', 'Cat 1', '["url1","url2"]', '[{"id":1,"name":"tag1"},{"id":2,"name":"tag2"}]', 'available'),
    (2, '{"id":2,"name":"Cats"}', 'Cat 2', '["url1","url2"]', '[{"id":1,"name":"tag2"},{"id":2,"name":"tag3"}]', 'available'),
    (3, '{"id":2,"name":"Cats"}', 'Cat 3', '["url1","url2"]', '[{"id":1,"name":"tag3"},{"id":2,"name":"tag4"}]', 'pending'),
    (4, '{"id":1,"name":"Dogs"}', 'Dog 1', '["url1","url2"]', '[{"id":1,"name":"tag1"},{"id":2,"name":"tag2"}]', 'available'),
    (5, '{"id":1,"name":"Dogs"}', 'Dog 2', '["url1","url2"]', '[{"id":1,"name":"tag2"},{"id":2,"name":"tag3"}]', 'sold'),
    (6, '{"id":1,"name":"Dogs"}', 'Dog 3', '["url1","url2"]', '[{"id":1,"name":"tag3"},{"id":2,"name":"tag4"}]', 'pending'),
    (7, '{"id":4,"name":"Lions"}', 'Lion 1', '["url1","url2"]', '[{"id":1,"name":"tag1"},{"id":2,"name":"tag2"}]', 'available'),
    (8, '{"id":4,"name":"Lions"}', 'Lion 2', '["url1","url2"]', '[{"id":1,"name":"tag2"},{"id":2,"name":"tag3"}]', 'available'),
    (9, '{"id":4,"name":"Lions"}', 'Lion 3', '["url1","url2"]', '[{"id":1,"name":"tag3"},{"id":2,"name":"tag4"}]', 'available'),
    (10, '{"id":3,"name":"Rabbits"}', 'Rabbit 1', '["url1","url2"]', '[{"id":1,"name":"tag3"},{"id":2,"name":"tag4"}]', 'available')
ON CONFLICT (id) DO NOTHING;

INSERT INTO store_orders
    (id, pet_id, quantity, ship_date, status, complete, owner_username)
VALUES
    (1, 1, 2, CURRENT_TIMESTAMP, 'placed', FALSE, 'user1'),
    (2, 4, 1, CURRENT_TIMESTAMP, 'approved', FALSE, 'user1'),
    (3, 7, 1, CURRENT_TIMESTAMP, 'delivered', TRUE, 'admin')
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users), TRUE);
SELECT setval(pg_get_serial_sequence('pets', 'id'), (SELECT MAX(id) FROM pets), TRUE);
SELECT setval(pg_get_serial_sequence('store_orders', 'id'), (SELECT MAX(id) FROM store_orders), TRUE);
