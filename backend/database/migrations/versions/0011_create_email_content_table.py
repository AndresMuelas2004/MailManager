"""
Create email_content table for storing full email body content.

Separate table from email_metadata because metadata is queried in bulk
(listing) while content is queried one row at a time (viewing).
"""
from __future__ import annotations

from alembic import op


revision = "0011_create_email_content_table"
down_revision = "0010_seed_fake_data_for_get_tests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_content (
            provider_message_id  VARCHAR(255) NOT NULL,
            account_id           UUID         NOT NULL
                                 REFERENCES accounts(account_id) ON DELETE CASCADE,
            html_body            TEXT,
            text_body            TEXT,
            fetched_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
            PRIMARY KEY (provider_message_id, account_id)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_content;")
