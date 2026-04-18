"""
One-shot invalidation of the email_content cache (sixth round).

The HTML rendering pipeline was hardened against a family of bugs that cost
the body content of certain provider emails (Pencil.dev #36, Artlist #56,
Eurofirms #473) and caused visible duplication on templates that ship both
an Outlook-only block and a non-Outlook block (Medusa Festival #20,
Santander Open Academy #73), a lost HubSpot/Netcapital outer background
(#8, #9) and preheader text leaking through broken ``<style>`` blocks
(#5, #22, #51, #73, #84, #143, #315). Concretely:

- ``<title>``, ``<!DOCTYPE>``, ``<meta>``, ``<link>``, ``<base>`` and stray
  ``<xml>`` islands are now removed before lxml's fragment parser runs.
  Head-only elements that survive a flatten step push libxml2 into parsing
  modes that silently drop sibling body content — the ``<title>`` text
  previously leaked as visible text on Pencil.dev; lxml reorganised Artlist
  and Eurofirms into fragments missing all their real body content.
- ``<body style="…">`` and ``<body bgcolor="…">`` are now promoted to an
  outer ``<div>`` so the HubSpot-style lavender background survives the
  iframe's own ``body{background:#fff}`` reset in the viewer.
- The MSO conditional unwrap now DISCARDS downlevel-hidden
  ``<!--[if mso | IE]>…<![endif]-->`` blocks entirely. We render inside a
  sandboxed web iframe — not Outlook — so content meant to be invisible in
  non-MSO clients must stay invisible. Unwrapping it caused adjacent
  MSO/non-MSO pairs to render twice.
- ``_sanitize_css_rules`` now tolerates a single unparseable CSS rule
  instead of wiping the whole ``<style>`` block. Preheader-hiding rules
  like ``.preheader{display:none}`` sitting next to a malformed sibling
  survive and premailer inlines them onto the target element.
- ``_mirror_geometry_to_attributes`` now ignores its own output when
  lxml's fragment reparse shrinks the content by more than 50 %. The
  width/height mirror is cosmetic; it must never cost us body content.

HTML cached before these changes would still render with the old pipeline's
output (empty body, duplicated logos, lost lavender background, visible
preheader). Truncating ``email_content`` forces cache-aside refetch on next
view, producing correctly rendered content on the refactored pipeline.

Does not alter the schema. ``ON DELETE CASCADE`` from ``email_metadata`` is
unaffected — only the cached rows are removed; metadata is intact and
repopulation is transparent to the user.
"""
from __future__ import annotations

from alembic import op


revision = "0019_invalidate_email_content_cache_pipeline_refactor"
down_revision = "0018_invalidate_email_content_cache_style_preservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE email_content;")


def downgrade() -> None:
    # One-shot cache invalidation. The cleared rows cannot be re-inflated
    # without re-fetching from the provider, which the cache-aside pattern
    # already handles on demand.
    pass
