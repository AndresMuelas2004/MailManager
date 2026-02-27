"""
Add users and sessions tables, and owner_user_id to mailboxes.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_auth_tables_and_mailbox_owner"
down_revision = "0002_tokens_encryption_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("google_sub", sa.String(length=255), nullable=False, unique=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_expires_at", "sessions", ["expires_at"])

    op.add_column(
        "mailboxes",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mailboxes_owner_user_id",
        "mailboxes",
        "users",
        ["owner_user_id"],
        ["user_id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_mailboxes_owner_user_id", "mailboxes", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("idx_mailboxes_owner_user_id", table_name="mailboxes")
    op.drop_constraint("fk_mailboxes_owner_user_id", "mailboxes", type_="foreignkey")
    op.drop_column("mailboxes", "owner_user_id")
    op.drop_index("idx_sessions_expires_at", table_name="sessions")
    op.drop_index("idx_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
