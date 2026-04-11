"""
Switch email_content to shared primary key with email_metadata.

Removes the direct FK to accounts and replaces it with a composite FK to
email_metadata(provider_message_id, account_id) ON DELETE CASCADE. The
cascade accounts -> email_metadata -> email_content becomes transitive,
preserving existing delete semantics. Defensive orphan cleanup runs first
so the migration is safe on databases where content was ever persisted
without a matching metadata row.
"""
from __future__ import annotations

from alembic import op


revision = "0013_email_content_shared_pk_fk"
down_revision = "0012_create_drafts_table"
branch_labels = None
depends_on = None


_OLD_FK_NAME = "email_content_account_id_fkey"
_NEW_FK_NAME = "email_content_metadata_fkey"


def upgrade() -> None:
    # 1. Drop orphan content rows that have no matching metadata row.
    op.execute("""
        DELETE FROM email_content ec
        WHERE NOT EXISTS (
            SELECT 1 FROM email_metadata em
            WHERE em.provider_message_id = ec.provider_message_id
              AND em.account_id          = ec.account_id
        );
    """)

    # 2. Drop the direct FK to accounts.
    op.drop_constraint(_OLD_FK_NAME, "email_content", type_="foreignkey")

    # 3. Add composite FK to email_metadata (cascade transitive via metadata).
    op.create_foreign_key(
        _NEW_FK_NAME,
        source_table="email_content",
        referent_table="email_metadata",
        local_cols=["provider_message_id", "account_id"],
        remote_cols=["provider_message_id", "account_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_NEW_FK_NAME, "email_content", type_="foreignkey")
    op.create_foreign_key(
        _OLD_FK_NAME,
        source_table="email_content",
        referent_table="accounts",
        local_cols=["account_id"],
        remote_cols=["account_id"],
        ondelete="CASCADE",
    )
