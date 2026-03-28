"""
Add email_address column to accounts table.
"""

from __future__ import annotations

from alembic import op


revision = "0009_add_email_address_to_accounts"
down_revision = "0008_add_previous_box_and_deleted_box"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE accounts "
        "ADD COLUMN IF NOT EXISTS email_address TEXT DEFAULT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE accounts "
        "DROP COLUMN IF EXISTS email_address"
    )
