"""
One-shot invalidation of the email_content cache.

After fixing the email HTML pipeline (CSS inlining via premailer in
``sanitize_email_html`` and ``cid:`` resolution for inline images in the
Gmail/Outlook clients), any previously cached HTML would still render
flat and without inline images. Truncating ``email_content`` forces the
cache-aside pattern in ``get_email_full_content`` to refetch the content
from the provider on next view, producing the corrected HTML.

Does not alter the schema. The ON DELETE CASCADE from ``email_metadata``
is unaffected — only the cached rows are removed; metadata is intact and
repopulation is transparent to the user.
"""
from __future__ import annotations

from alembic import op


revision = "0014_invalidate_email_content_cache"
down_revision = "0013_email_content_shared_pk_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE email_content;")


def downgrade() -> None:
    # One-shot cache invalidation. The cleared rows cannot be re-inflated
    # without re-fetching from the provider, which the cache-aside pattern
    # already handles on demand.
    pass
