"""
Fallback migration runner used when Alembic is unavailable.
"""

from __future__ import annotations

from typing import Any

import psycopg2

from database.errors.exceptions import MigrationError


_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id    UUID         PRIMARY KEY,
        google_sub VARCHAR(255) UNIQUE NOT NULL,
        email      VARCHAR(320) NOT NULL,
        name       VARCHAR(200),
        avatar_url TEXT,
        created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS mailboxes (
        mailbox_id    UUID         PRIMARY KEY,
        display_name  VARCHAR(120) NOT NULL,
        owner_user_id UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_mailboxes_owner_user_id ON mailboxes(owner_user_id);",
    """
    CREATE TABLE IF NOT EXISTS accounts (
        account_id              UUID         PRIMARY KEY,
        mailbox_id              UUID         NOT NULL
                                REFERENCES mailboxes(mailbox_id) ON DELETE CASCADE,
        provider                VARCHAR(20)  NOT NULL
                                CHECK (provider IN ('gmail', 'outlook')),
        display_label           VARCHAR(120) NOT NULL,
        config                  JSONB        NOT NULL DEFAULT '{}'::jsonb,
        created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
        access_token            TEXT,
        refresh_token           TEXT,
        access_token_encrypted  TEXT,
        refresh_token_encrypted TEXT,
        encryption_key_id       VARCHAR(64),
        expiry                  TIMESTAMPTZ,
        scopes                  TEXT[],
        tokens_updated_at       TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_accounts_mailbox_id ON accounts(mailbox_id);",
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id UUID        PRIMARY KEY,
        user_id    UUID        NOT NULL
                   REFERENCES users(user_id) ON DELETE CASCADE,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);",
    # Backward compatibility: these ALTERs are no-ops on fresh databases but ensure
    # databases created before migration 0003/0004 are brought up to date.
    "ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(user_id) ON DELETE CASCADE;",
    "DELETE FROM mailboxes WHERE owner_user_id IS NULL;",
    "ALTER TABLE mailboxes ALTER COLUMN owner_user_id SET NOT NULL;",
    """
    CREATE TABLE IF NOT EXISTS alembic_version (
        version_num VARCHAR(64) PRIMARY KEY
    );
    """,
    # Migrations 0006–0007: sync_cursor + email_metadata + SENT box value
    "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS sync_cursor TEXT;",
    """
    CREATE TABLE IF NOT EXISTS email_metadata (
        provider_message_id  VARCHAR(255) NOT NULL,
        account_id           UUID         NOT NULL
                             REFERENCES accounts(account_id) ON DELETE CASCADE,
        thread_id            VARCHAR(255),
        from_email           VARCHAR(320) NOT NULL,
        from_name            VARCHAR(200) DEFAULT '',
        subject              TEXT         NOT NULL DEFAULT '',
        received_at          TIMESTAMPTZ  NOT NULL,
        is_read              BOOLEAN      NOT NULL DEFAULT FALSE,
        box                  VARCHAR(20)  NOT NULL DEFAULT 'ALL_MAIL'
                             CHECK (box IN ('ALL_MAIL', 'SPAM', 'TRASH', 'SENT', 'DELETED')),
        previous_box         VARCHAR(20)  DEFAULT NULL
                             CHECK (previous_box IS NULL OR previous_box IN ('ALL_MAIL', 'SENT', 'SPAM')),
        PRIMARY KEY (provider_message_id, account_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_email_metadata_account_id ON email_metadata(account_id);",
    "CREATE INDEX IF NOT EXISTS idx_email_metadata_received_at ON email_metadata(received_at DESC);",
    "DELETE FROM alembic_version;",
    "INSERT INTO alembic_version(version_num) VALUES ('0008_add_previous_box_and_deleted_box');",
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
        raise MigrationError(
            "Failed to apply fallback database migrations."
        ) from exc
    except Exception as exc:
        raise MigrationError(
            f"Unexpected migration error ({type(exc).__name__}): {exc}"
        ) from exc
