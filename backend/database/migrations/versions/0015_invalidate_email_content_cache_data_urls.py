"""
One-shot invalidation of the email_content cache (second round).

After extending the sanitizer's allowed protocols to include ``data:``
(``_SANITIZE_ALLOWED_PROTOCOLS`` in ``api/services/services_helpers.py``),
any HTML cached before this change would still carry ``<img>`` tags whose
``src="data:..."`` attribute was stripped by bleach, leaving inline images
broken. Truncating ``email_content`` forces the cache-aside pattern in
``get_email_full_content`` to refetch and re-sanitize on next view, so the
inline images (logos, signatures) render correctly.

Does not alter the schema. The ON DELETE CASCADE from ``email_metadata``
is unaffected — only the cached rows are removed; metadata is intact and
repopulation is transparent to the user.
"""
from __future__ import annotations

from alembic import op


revision = "0015_invalidate_email_content_cache_data_urls"
down_revision = "0014_invalidate_email_content_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE email_content;")


def downgrade() -> None:
    # One-shot cache invalidation. The cleared rows cannot be re-inflated
    # without re-fetching from the provider, which the cache-aside pattern
    # already handles on demand.
    pass
