"""
Fallback migration runner used when Alembic is unavailable.
"""

from __future__ import annotations

from typing import Any

import psycopg2

from api.errors.exceptions import DatabaseError


_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS mailboxes (
        mailbox_id   UUID         PRIMARY KEY,
        display_name VARCHAR(120) NOT NULL,
        created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
    );
    """,
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS idx_accounts_mailbox_id ON accounts(mailbox_id);",
    """
    CREATE TABLE IF NOT EXISTS tokens (
        account_id              UUID         PRIMARY KEY
                                REFERENCES accounts(account_id) ON DELETE CASCADE,
        access_token            TEXT,
        refresh_token           TEXT,
        expiry                  TIMESTAMPTZ,
        scopes                  TEXT[],
        updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
    );
    """,
    "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT;",
    "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT;",
    "ALTER TABLE tokens ADD COLUMN IF NOT EXISTS encryption_key_id VARCHAR(64);",
    """
    CREATE TABLE IF NOT EXISTS alembic_version (
        version_num VARCHAR(64) PRIMARY KEY
    );
    """,
    "DELETE FROM alembic_version;",
    "INSERT INTO alembic_version(version_num) VALUES ('0002_tokens_encryption_columns');",
]


def _apply_statements(cur: Any) -> None:
    for statement in _DDL_STATEMENTS:
        cur.execute(statement)


def ensure_schema_at_head(dsn: str) -> None:
    """
    Apply idempotent head schema without Alembic runtime dependency.
    """
    try:
        with psycopg2.connect(dsn=dsn) as conn:
            with conn.cursor() as cur:
                _apply_statements(cur)
    except psycopg2.Error as exc:
        raise DatabaseError("Failed to apply fallback database migrations.") from exc

