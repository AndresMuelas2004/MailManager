"""Enable unaccent extension for accent-insensitive email search."""

from __future__ import annotations

from alembic import op


revision = "0020_create_extension_unaccent"
down_revision = "0019_invalidate_email_content_cache_pipeline_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS unaccent;")
