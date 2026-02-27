"""
Merge tokens table into accounts (1:1 relationship elimination).
"""

from __future__ import annotations

from alembic import op


revision = "0005_merge_tokens_into_accounts"
down_revision = "0004_owner_user_id_not_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add token columns (all nullable) to accounts.
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS access_token TEXT")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS refresh_token TEXT")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS encryption_key_id VARCHAR(64)")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS expiry TIMESTAMPTZ")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS scopes TEXT[]")
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS tokens_updated_at TIMESTAMPTZ")

    # 2. Copy data from tokens into accounts.
    op.execute(
        """
        UPDATE accounts AS a
           SET access_token            = t.access_token,
               refresh_token           = t.refresh_token,
               access_token_encrypted  = t.access_token_encrypted,
               refresh_token_encrypted = t.refresh_token_encrypted,
               encryption_key_id       = t.encryption_key_id,
               expiry                  = t.expiry,
               scopes                  = t.scopes,
               tokens_updated_at       = t.updated_at
          FROM tokens AS t
         WHERE a.account_id = t.account_id
        """
    )

    # 3. Drop the now-redundant tokens table.
    op.execute("DROP TABLE IF EXISTS tokens")


def downgrade() -> None:
    # 1. Recreate the tokens table.
    op.execute(
        """
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
        )
        """
    )

    # 2. Copy token data back from accounts.
    op.execute(
        """
        INSERT INTO tokens (
            account_id, access_token, refresh_token,
            access_token_encrypted, refresh_token_encrypted,
            encryption_key_id, expiry, scopes, updated_at
        )
        SELECT
            account_id, access_token, refresh_token,
            access_token_encrypted, refresh_token_encrypted,
            encryption_key_id, expiry, scopes,
            COALESCE(tokens_updated_at, now())
        FROM accounts
        WHERE access_token IS NOT NULL
           OR refresh_token IS NOT NULL
           OR access_token_encrypted IS NOT NULL
           OR refresh_token_encrypted IS NOT NULL
        """
    )

    # 3. Drop token columns from accounts.
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS access_token")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS refresh_token")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS access_token_encrypted")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS refresh_token_encrypted")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS encryption_key_id")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS expiry")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS scopes")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS tokens_updated_at")
