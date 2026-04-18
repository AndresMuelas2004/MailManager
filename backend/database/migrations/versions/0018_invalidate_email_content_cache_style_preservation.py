"""
One-shot invalidation of the email_content cache (fifth round).

The HTML rendering pipeline was refactored into a dedicated module
(``api.services.email_html_pipeline``) and the sanitization strategy was
upgraded so that ``<style>`` blocks survive the pipeline instead of being
stripped. Concretely:

- ``<style>`` content is now parsed with cssutils, filtered against the
  property allowlist, and kept alongside the HTML. This preserves ``@media``
  queries, pseudo-class rules (``:hover``), and corporate ``@font-face``
  declarations that mobile-first newsletter templates rely on to unveil the
  desktop layout. Without this fix, responsive newsletters (eDreams,
  Netcapital, HubSpot-style templates) rendered only their mobile preheader
  because the desktop overrides lived inside ``@media`` rules that premailer
  used to drop.
- Premailer now runs with ``keep_style_tags=True`` so the sanitised
  ``<style>`` tag survives and its rules apply inside the iframe viewer.
- Gmail body decoding switched to UTF-8-first with validated fallback to the
  declared charset, eliminating mojibake on senders that mislabel UTF-8
  bodies as ``iso-8859-1``/``windows-1252``.

HTML cached before these changes would still render with the old pipeline's
output (no responsive layout, potential mojibake on Gmail plain-text
replies). Truncating ``email_content`` forces cache-aside refetch on next
view, producing correctly rendered content on the new pipeline.

Does not alter the schema. ``ON DELETE CASCADE`` from ``email_metadata`` is
unaffected — only the cached rows are removed; metadata is intact and
repopulation is transparent to the user.
"""
from __future__ import annotations

from alembic import op


revision = "0018_invalidate_email_content_cache_style_preservation"
down_revision = "0017_invalidate_email_content_cache_charset_geometry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE email_content;")


def downgrade() -> None:
    # One-shot cache invalidation. The cleared rows cannot be re-inflated
    # without re-fetching from the provider, which the cache-aside pattern
    # already handles on demand.
    pass
