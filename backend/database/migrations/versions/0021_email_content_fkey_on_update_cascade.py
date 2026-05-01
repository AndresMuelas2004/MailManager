"""
Add ON UPDATE CASCADE to the email_content -> email_metadata foreign key.

Outlook mutates the provider_message_id when an email is moved between
folders (e.g. inbox -> trash). The MOVE_TO_TRASH_BATCH query updates the
metadata row's provider_message_id to the new value. With the original FK
defined as ON DELETE CASCADE only (default ON UPDATE NO ACTION), any
previously cached email_content row blocks the parent's PK update with a
ForeignKeyViolation. Adding ON UPDATE CASCADE lets the cached content row
follow the parent's new id automatically.
"""
from __future__ import annotations

from alembic import op


revision = "0021_email_content_fkey_on_update_cascade"
down_revision = "0020_create_extension_unaccent"
branch_labels = None
depends_on = None


_FK_NAME = "email_content_metadata_fkey"


def upgrade() -> None:
    op.drop_constraint(_FK_NAME, "email_content", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        source_table="email_content",
        referent_table="email_metadata",
        local_cols=["provider_message_id", "account_id"],
        remote_cols=["provider_message_id", "account_id"],
        ondelete="CASCADE",
        onupdate="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, "email_content", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        source_table="email_content",
        referent_table="email_metadata",
        local_cols=["provider_message_id", "account_id"],
        remote_cols=["provider_message_id", "account_id"],
        ondelete="CASCADE",
    )
