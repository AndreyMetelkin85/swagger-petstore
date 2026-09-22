CREATE INDEX idx_users_reset_code_hash
    ON users (reset_code_hash)
    WHERE reset_code_hash IS NOT NULL;
