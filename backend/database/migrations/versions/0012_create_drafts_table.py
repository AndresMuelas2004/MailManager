"""
Create drafts table for storing provider-backed draft emails.

Drafts are persisted in a separate table from email_metadata because:
- They are created via a different API path (drafts endpoint, not metadata sync).
- Recipients require TEXT[] arrays (email_metadata has scalar from_email).
- They may exist at the provider without ever being sent.
"""
from __future__ import annotations

from alembic import op


revision = "0012_create_drafts_table"
down_revision = "0011_create_email_content_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            provider_draft_id VARCHAR(255) NOT NULL,
            account_id        UUID         NOT NULL
                              REFERENCES accounts(account_id) ON DELETE CASCADE,
            to_recipients     TEXT[]       NOT NULL DEFAULT '{}',
            cc_recipients     TEXT[]       NOT NULL DEFAULT '{}',
            bcc_recipients    TEXT[]       NOT NULL DEFAULT '{}',
            subject           TEXT         NOT NULL DEFAULT '',
            body_html         TEXT         NOT NULL DEFAULT '',
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            PRIMARY KEY (provider_draft_id, account_id)
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drafts_account_id ON drafts(account_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_drafts_account_id;")
    op.execute("DROP TABLE IF EXISTS drafts;")
