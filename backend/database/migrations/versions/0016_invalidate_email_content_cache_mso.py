"""
One-shot invalidation of the email_content cache (third round).

After three follow-up fixes to the email HTML pipeline:
- Unwrapping MSO/IE conditional comments in the sanitizer so Outlook's
  desktop-optimized layout survives (previously stripped by bleach/
  premailer, leaving only the mobile placeholders that collapse to
  ~4% width).
- Extending ``inline_cid_images`` to resolve ``cid:`` inside CSS
  ``url(...)`` functions (e.g. ``background-image:url(cid:…)`` that
  premailer inlines from ``<style>`` blocks).
- Respecting the MIME part charset in Gmail's body decoder instead of
  assuming UTF-8 (non-UTF-8 emails would otherwise decode to ``None``
  silently).

Any HTML cached before these changes would still render collapsed
(Outlook signatures), keep broken ``cid:`` references inside CSS
background-image, or be missing entirely for non-UTF-8 emails.
Truncating ``email_content`` forces cache-aside refetch on next view,
producing correctly rendered content.

Does not alter the schema. ``ON DELETE CASCADE`` from ``email_metadata``
is unaffected — only the cached rows are removed; metadata is intact and
repopulation is transparent to the user.
"""
from __future__ import annotations

from alembic import op


revision = "0016_invalidate_email_content_cache_mso"
down_revision = "0015_invalidate_email_content_cache_data_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE email_content;")


def downgrade() -> None:
    # One-shot cache invalidation. The cleared rows cannot be re-inflated
    # without re-fetching from the provider, which the cache-aside pattern
    # already handles on demand.
    pass
