"""
Add previous_box column and DELETED to box CHECK constraint in email_metadata.
"""

from __future__ import annotations

from alembic import op


revision = "0008_add_previous_box_and_deleted_box"
down_revision = "0007_add_sent_box_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_metadata "
        "ADD COLUMN IF NOT EXISTS previous_box VARCHAR(20) DEFAULT NULL"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP CONSTRAINT IF EXISTS email_metadata_previous_box_check"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "ADD CONSTRAINT email_metadata_previous_box_check "
        "CHECK (previous_box IN ('ALL_MAIL', 'SENT', 'SPAM'))"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP CONSTRAINT IF EXISTS email_metadata_box_check"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "ADD CONSTRAINT email_metadata_box_check "
        "CHECK (box IN ('ALL_MAIL', 'SENT', 'SPAM', 'TRASH', 'DELETED'))"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE email_metadata SET box = 'TRASH' WHERE box = 'DELETED'"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP CONSTRAINT IF EXISTS email_metadata_box_check"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "ADD CONSTRAINT email_metadata_box_check "
        "CHECK (box IN ('ALL_MAIL', 'SENT', 'SPAM', 'TRASH'))"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP CONSTRAINT IF EXISTS email_metadata_previous_box_check"
    )
    op.execute(
        "ALTER TABLE email_metadata "
        "DROP COLUMN IF EXISTS previous_box"
    )
