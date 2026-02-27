"""
Remove orphaned mailboxes and make owner_user_id NOT NULL.
"""

from __future__ import annotations

from alembic import op


revision = "0004_owner_user_id_not_null"
down_revision = "0003_auth_tables_and_mailbox_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM mailboxes WHERE owner_user_id IS NULL")
    op.alter_column("mailboxes", "owner_user_id", nullable=False)


def downgrade() -> None:
    op.alter_column("mailboxes", "owner_user_id", nullable=True)
