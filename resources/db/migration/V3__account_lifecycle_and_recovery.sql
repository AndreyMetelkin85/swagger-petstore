CREATE TYPE account_status AS ENUM ('PENDING', 'ACTIVE', 'BLOCKED');

ALTER TABLE users ADD COLUMN account_status_new account_status;
UPDATE users SET account_status_new = 'ACTIVE';
ALTER TABLE users ALTER COLUMN account_status_new SET NOT NULL;
ALTER TABLE users ALTER COLUMN account_status_new SET DEFAULT 'PENDING';
ALTER TABLE users DROP COLUMN user_status;
ALTER TABLE users RENAME COLUMN account_status_new TO user_status;

ALTER TABLE users ADD COLUMN confirmed_at TIMESTAMPTZ;
UPDATE users SET confirmed_at = CURRENT_TIMESTAMP;

ALTER TABLE users ADD COLUMN confirmation_code_hash CHAR(64);
ALTER TABLE users ADD COLUMN confirmation_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN reset_code_hash CHAR(64);
ALTER TABLE users ADD COLUMN reset_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN reset_used_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX uq_users_email_lower ON users (LOWER(email));
CREATE INDEX idx_users_status ON users (user_status);
