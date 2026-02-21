-- ============================================================
-- MailManager - Database Schema Snapshot (legacy reference)
-- Source of truth for schema evolution: Alembic migrations.
-- ============================================================

-- ---------- MAILBOXES ----------

CREATE TABLE IF NOT EXISTS mailboxes (
    mailbox_id   UUID         PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------- ACCOUNTS ----------

CREATE TABLE IF NOT EXISTS accounts (
    account_id    UUID         PRIMARY KEY,
    mailbox_id    UUID         NOT NULL
                  REFERENCES mailboxes(mailbox_id) ON DELETE CASCADE,
    provider      VARCHAR(20)  NOT NULL
                  CHECK (provider IN ('gmail', 'outlook')),
    display_label VARCHAR(120) NOT NULL,
    config        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_accounts_mailbox_id
    ON accounts(mailbox_id);

-- ---------- TOKENS ----------

CREATE TABLE IF NOT EXISTS tokens (
    account_id              UUID         PRIMARY KEY
                            REFERENCES accounts(account_id) ON DELETE CASCADE,
    access_token            TEXT,
    refresh_token           TEXT,
    access_token_encrypted  TEXT,
    refresh_token_encrypted TEXT,
    encryption_key_id       VARCHAR(64),
    expiry                  TIMESTAMPTZ,
    scopes                  TEXT[],
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
);
