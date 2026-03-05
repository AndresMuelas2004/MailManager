"""
Add sync_cursor to accounts and create email_metadata table.
"""

from __future__ import annotations

from alembic import op


revision = "0006_sync_cursor_and_email_metadata"
down_revision = "0005_merge_tokens_into_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS sync_cursor TEXT")

    op.execute(
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
                                 CHECK (box IN ('ALL_MAIL', 'SPAM', 'TRASH')),
            PRIMARY KEY (provider_message_id, account_id)
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_metadata_account_id "
        "ON email_metadata(account_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_metadata_received_at "
        "ON email_metadata(received_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_metadata")
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS sync_cursor")
