"""
Add SENT to the box CHECK constraint in email_metadata.
"""

from __future__ import annotations

from alembic import op


revision = "0007_add_sent_box_value"
down_revision = "0006_sync_cursor_and_email_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP CONSTRAINT IF EXISTS email_metadata_box_check"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "ADD CONSTRAINT email_metadata_box_check "
        "CHECK (box IN ('ALL_MAIL', 'SENT', 'SPAM', 'TRASH'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP CONSTRAINT IF EXISTS email_metadata_box_check"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "ADD CONSTRAINT email_metadata_box_check "
        "CHECK (box IN ('ALL_MAIL', 'SPAM', 'TRASH'))"
    )
