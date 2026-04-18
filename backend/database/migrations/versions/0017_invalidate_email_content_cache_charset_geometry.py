"""
One-shot invalidation of the email_content cache (fourth round).

After two follow-up fixes to the email HTML pipeline:
- Forcing UTF-8 on the downstream parsers by stripping bogus charset metas
  (``<meta http-equiv="Content-Type" content="text/html; charset=us-ascii">``
  and ``<meta charset="windows-1252">``) that Outlook injects. Without this,
  premailer (lxml) and bleach (html5lib) re-interpreted UTF-8 bytes as
  Latin-1, producing mojibake like ``prÃ¡cticas`` instead of ``prácticas``.
- Mirroring ``width``/``height`` values from inline styles back onto HTML
  attributes on ``<img>``/``<td>``/``<th>``/``<table>``. Premailer drops
  the original attribute after inlining; if any later pass loses the
  style, the element would reflow to min-content and collapse the layout
  (narrow signature columns, shrunk logos).

Any HTML cached before these changes would still render with accented
characters corrupted or with signature tables collapsed to the width of the
longest word. Truncating ``email_content`` forces cache-aside refetch on
next view, producing correctly rendered content.

Does not alter the schema. ``ON DELETE CASCADE`` from ``email_metadata``
is unaffected — only the cached rows are removed; metadata is intact and
repopulation is transparent to the user.
"""
from __future__ import annotations

from alembic import op


revision = "0017_invalidate_email_content_cache_charset_geometry"
down_revision = "0016_invalidate_email_content_cache_mso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE email_content;")


def downgrade() -> None:
    # One-shot cache invalidation. The cleared rows cannot be re-inflated
    # without re-fetching from the provider, which the cache-aside pattern
    # already handles on demand.
    pass
