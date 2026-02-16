-- ============================================================
-- MailManager – Database Schema (DDL)
-- PostgreSQL 18
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
    account_id    UUID        PRIMARY KEY
                  REFERENCES accounts(account_id) ON DELETE CASCADE,
    access_token  TEXT,
    refresh_token TEXT,
    expiry        TIMESTAMPTZ,
    scopes        TEXT[],
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
