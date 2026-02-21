"""
Add encrypted token columns and key id.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_tokens_encryption_columns"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tokens", sa.Column("access_token_encrypted", sa.Text(), nullable=True))
    op.add_column("tokens", sa.Column("refresh_token_encrypted", sa.Text(), nullable=True))
    op.add_column("tokens", sa.Column("encryption_key_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("tokens", "encryption_key_id")
    op.drop_column("tokens", "refresh_token_encrypted")
    op.drop_column("tokens", "access_token_encrypted")

