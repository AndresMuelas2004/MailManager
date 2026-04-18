"""
Unit tests for the email HTML pipeline (``prepare_email_html``).

The public entry point is re-exported from ``services_helpers`` under the
legacy name ``sanitize_email_html`` so existing callers keep working. These
tests import the legacy alias to exercise the full pipeline end-to-end.
"""

from __future__ import annotations

from api.services.services_helpers import sanitize_email_html


# ---------------------------------------------------------------------------
# Script / event handler / dangerous protocol removal
# ---------------------------------------------------------------------------


def test_strips_script_tags():
    result = sanitize_email_html("<p>hello</p><script>alert(1)</script>")
    assert "<script>" not in result
    assert "alert(1)" not in result
    assert "<p>hello</p>" in result


def test_preserves_safe_tags():
    html = '<p>Text</p><b>Bold</b><a href="https://example.com">Link</a><img src="https://img.png" alt="img">'
    result = sanitize_email_html(html)
    assert "<p>" in result
    assert "<b>" in result
    assert "<a " in result
    assert "<img " in result


def test_strips_event_handlers():
    html = '<div onclick="alert(1)">click me</div>'
    result = sanitize_email_html(html)
    assert "onclick" not in result
    assert "click me" in result


def test_blocks_javascript_href():
    html = '<a href="javascript:alert(1)">evil</a>'
    result = sanitize_email_html(html)
    assert "javascript:" not in result


def test_allows_mailto_href():
    html = '<a href="mailto:test@example.com">mail</a>'
    result = sanitize_email_html(html)
    assert 'href="mailto:test@example.com"' in result


def test_allows_cid_img_src():
    html = '<img src="cid:image001">'
    result = sanitize_email_html(html)
    assert 'src="cid:image001"' in result


def test_allows_data_url_img_src():
    html = '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==" alt="logo">'
    result = sanitize_email_html(html)
    assert 'src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="' in result


def test_empty_string_returns_empty():
    assert sanitize_email_html("") == ""


def test_whitespace_returns_as_is():
    assert sanitize_email_html("   ") == "   "


def test_strips_onerror_on_img():
    html = '<img src="x" onerror="alert(1)">'
    result = sanitize_email_html(html)
    assert "onerror" not in result
    assert "<img " in result


# ---------------------------------------------------------------------------
# CSS inlining and <style> preservation
# ---------------------------------------------------------------------------


def test_inlines_style_rules_into_attributes():
    """Simple rules still get inlined for compatibility with strict clients."""
    html = "<html><head><style>p{color:red}</style></head><body><p>hi</p></body></html>"
    result = sanitize_email_html(html)
    # premailer inlines the rule onto the <p> tag
    assert "color:red" in result.replace(" ", "")


def test_inlines_class_selectors():
    html = (
        "<html><head><style>.btn{background:#1a73e8;color:#fff}</style></head>"
        "<body><a class=\"btn\" href=\"https://example.com\">click</a></body></html>"
    )
    result = sanitize_email_html(html)
    normalized = result.replace(" ", "").lower()
    assert "background:#1a73e8" in normalized
    assert "color:#fff" in normalized


def test_preserves_media_queries_in_style_block():
    """``@media`` queries must survive so responsive desktop layouts render."""
    html = (
        "<html><head><style>"
        ".mobile-hide{display:none}"
        "@media (min-width:600px){.mobile-hide{display:block}.desktop-only{display:block}}"
        "</style></head><body>"
        '<div class="mobile-hide">desktop content</div>'
        '<div class="desktop-only">extra</div>'
        "</body></html>"
    )
    result = sanitize_email_html(html)
    # The <style> block is kept so the browser can apply the @media override
    # at the iframe viewport width. Without this the two divs would stay
    # display:none and the email would render empty (eDreams/Netcapital bug).
    assert "@media" in result
    assert "min-width" in result
    assert "desktop content" in result
    assert "extra" in result


def test_preserves_pseudo_class_rules():
    """Pseudo-classes (``:hover``) are not inlinable — must survive in <style>."""
    html = (
        "<html><head><style>"
        "a{color:#333}"
        "a:hover{color:#1a73e8;text-decoration:underline}"
        "</style></head><body>"
        '<a href="https://example.com">link</a>'
        "</body></html>"
    )
    result = sanitize_email_html(html)
    assert ":hover" in result
    normalized = result.replace(" ", "").lower()
    assert "color:#1a73e8" in normalized


def test_style_block_strips_dangerous_expression():
    html = (
        "<html><head><style>"
        "div{width:expression(alert(1))}"
        "</style></head><body><div>hi</div></body></html>"
    )
    result = sanitize_email_html(html)
    assert "expression(" not in result
    assert "alert(1)" not in result


def test_style_block_strips_dangerous_url_scheme():
    html = (
        "<html><head><style>"
        "body{background:url(javascript:alert(1))}"
        "</style></head><body>x</body></html>"
    )
    result = sanitize_email_html(html)
    assert "javascript:" not in result


def test_style_block_strips_import_rule():
    """``@import`` would fetch remote CSS — must be dropped."""
    html = (
        "<html><head><style>"
        "@import url('https://evil.example.com/steal.css');"
        "p{color:red}"
        "</style></head><body><p>hi</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "@import" not in result
    assert "evil.example.com" not in result
    # The rest of the stylesheet still works
    assert "color:red" in result.replace(" ", "")


def test_style_block_strips_unknown_at_rules():
    """``@keyframes`` (animation) is not in the allow-list — must be dropped."""
    html = (
        "<html><head><style>"
        "@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}"
        "p{color:red}"
        "</style></head><body><p>hi</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "@keyframes" not in result
    assert "rotate" not in result
    # The rest survives
    assert "color:red" in result.replace(" ", "")


def test_premailer_failure_falls_back(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated premailer failure")

    import premailer
    monkeypatch.setattr(premailer, "transform", boom)
    html = "<p>hello</p><script>alert(1)</script>"
    result = sanitize_email_html(html)
    # Falls back to bleach-only: script stripped, content preserved
    assert "<script>" not in result
    assert "<p>hello</p>" in result


def test_inlining_does_not_break_cid_img_src():
    html = (
        "<html><head><style>img{border:0}</style></head>"
        "<body><img src=\"cid:logo@x\"></body></html>"
    )
    result = sanitize_email_html(html)
    assert 'src="cid:logo@x"' in result


# ---------------------------------------------------------------------------
# MSO / IE conditional comment unwrap
# ---------------------------------------------------------------------------


def test_discards_mso_hidden_conditional_desktop_layout():
    """Outlook-only (downlevel-hidden) blocks are discarded, not unwrapped.

    The pipeline renders inside an iframe which is NOT Outlook/IE, so any
    content wrapped in ``<!--[if mso | IE]>…<![endif]-->`` is invisible to
    our client. Previously we unwrapped it, which caused visible duplication
    whenever templates shipped both an MSO-only desktop variant AND a
    non-MSO variant (Medusa Festival #20, Santander Open Academy #73).
    """
    html = (
        '<!--[if mso | IE]>'
        '<table width="600"><tr><td>DESKTOP</td></tr></table>'
        '<![endif]-->'
        '<table width="4%"><tr><td>MOBILE</td></tr></table>'
    )
    result = sanitize_email_html(html)
    # Outlook-only DESKTOP block is gone
    assert "DESKTOP" not in result
    # Non-MSO mobile placeholder stays
    assert "MOBILE" in result


def test_unwraps_non_mso_conditional():
    html = (
        "<!--[if !mso]><!-->"
        "<p>FALLBACK</p>"
        "<!--<![endif]-->"
    )
    result = sanitize_email_html(html)
    assert "FALLBACK" in result


def test_unwraps_downlevel_revealed_short_form():
    """eDreams/Outlook newsletter pattern: ``<!--[if !mso]><!-- -->…<!--<![endif]-->``.

    The short-form downlevel-revealed conditional uses nested comment markers
    (``<!-- -->`` / ``<!--``) to hide the ``[if …]`` tokens from standards-
    compliant parsers. If the regex leaves either half of those nested
    markers behind, html5lib treats the following markup as comment content
    and bleach drops big chunks of the email. This verifies both halves are
    stripped cleanly.
    """
    html = (
        '<!--[if !mso]><!-- -->'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        '<!--<![endif]-->'
        '<p>Body content must render.</p>'
    )
    result = sanitize_email_html(html)
    assert "Body content must render." in result
    # No stray unclosed comments, no leftover conditional tokens
    assert "<!--" not in result
    assert "[if" not in result
    assert "endif" not in result


def test_unwraps_mso_xml_island():
    """``<!--[if gte mso 9]><xml>…</xml><![endif]-->`` — Office XML settings.

    Common in newsletter HTML head. Must be fully stripped (or at least
    unwrapped) without leaving dangling comment markers that would confuse
    html5lib.
    """
    html = (
        '<!--[if gte mso 9]><xml>'
        '<o:OfficeDocumentSettings><o:AllowPNG/></o:OfficeDocumentSettings>'
        '</xml><![endif]-->'
        '<p>Still here.</p>'
    )
    result = sanitize_email_html(html)
    assert "Still here." in result
    assert "<!--" not in result


def test_mso_unwrap_ignores_malformed_conditional():
    # No closing <![endif]--> → the regex doesn't match; bleach then strips
    # the residual comment start. The inner tag survives intact.
    html = "<!--[if mso]><table>broken"
    result = sanitize_email_html(html)
    assert "<!--" not in result


# ---------------------------------------------------------------------------
# Charset normalisation — mojibake prevention
# ---------------------------------------------------------------------------


def test_strips_outlook_us_ascii_charset_meta():
    html = (
        '<html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=us-ascii"></head>'
        "<body><p>Prácticas</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "charset=us-ascii" not in result.lower()
    assert "Prácticas" in result


def test_strips_windows_1252_charset_meta():
    html = (
        '<html><head><meta charset="windows-1252"></head>'
        "<body><p>Gestión días Andrés</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "windows-1252" not in result.lower()
    assert "Gestión" in result
    assert "días" in result
    assert "Andrés" in result


def test_preserves_utf8_accented_characters_full_pipeline():
    html = (
        '<html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=us-ascii"></head>'
        "<body><p>Sí. Tenemos que tener firmado un convenio.</p>"
        "<p>Logroño (La Rioja)</p>"
        "<p>Teléfono: 941 299799</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "Sí" in result
    assert "Logroño" in result
    assert "Teléfono" in result
    # Ensure no mojibake sequences appear
    assert "Ã" not in result


def test_charset_normalisation_is_idempotent_on_correct_html():
    html = (
        '<html><head><meta charset="utf-8"></head>'
        "<body><p>Café résumé naïve</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "Café" in result
    assert "résumé" in result
    assert "naïve" in result
    assert "Ã" not in result


def test_charset_normalisation_skipped_without_head_tag():
    """Without a ``<head>``, no ``<meta charset>`` is injected — Python ``str``
    already arrives Unicode-decoded and prepending a ``<meta>`` before any
    DOCTYPE would push lxml into quirks mode.
    """
    html = '<p>Buenos días Andrés</p>'
    result = sanitize_email_html(html)
    assert "días" in result
    assert "Andrés" in result
    assert "Ã" not in result
    assert "<meta" not in result.lower()


# ---------------------------------------------------------------------------
# Geometry attribute restoration
# ---------------------------------------------------------------------------


def test_preserves_img_width_height_attributes():
    html = '<img src="https://example.com/logo.png" width="180" height="40">'
    result = sanitize_email_html(html)
    assert 'width="180"' in result
    assert 'height="40"' in result


def test_restores_width_from_inline_style_on_td():
    html = '<table><tr><td style="width: 500px">Text</td></tr></table>'
    result = sanitize_email_html(html)
    assert 'width="500"' in result


def test_restores_width_from_inline_style_on_table():
    html = '<table style="width: 600px"><tr><td>Cell</td></tr></table>'
    result = sanitize_email_html(html)
    assert 'width="600"' in result


def test_does_not_overwrite_existing_width_attribute():
    html = '<table width="400" style="width: 600px"><tr><td>Cell</td></tr></table>'
    result = sanitize_email_html(html)
    assert 'width="400"' in result


def test_signature_table_width_survives_full_pipeline():
    html = (
        "<html><head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=us-ascii">'
        "<style>td.logo{width:200px} td.info{width:400px}</style>"
        "</head><body>"
        '<table width="600"><tr>'
        '<td class="logo"><img src="cid:logo" width="180" height="50"></td>'
        '<td class="info">Natalia Capilla San Juan</td>'
        "</tr></table></body></html>"
    )
    result = sanitize_email_html(html)
    assert "Natalia Capilla San Juan" in result
    # Table should keep its 600px width (either as attribute or via restoration)
    assert 'width="600"' in result
    # Image dimensions should survive
    assert 'width="180"' in result
    assert 'height="50"' in result
    # No mojibake
    assert "Ã" not in result


# ---------------------------------------------------------------------------
# Head-level tags leaking into body after flatten (Pencil.dev / Artlist /
# Eurofirms family of bugs). Everything under <head> must be removed so lxml's
# fragment parser does not reorganise the tree and drop body-level content.
# ---------------------------------------------------------------------------


def test_strips_title_tag_and_content_so_subject_does_not_leak():
    """Bug #36 (Pencil.dev): the <title> text was rendering as body content.

    Before Fix A, ``<title>Subject X</title>`` survived into the body-level
    fragment; bleach strips the tag but keeps the inner text, which the
    iframe then rendered as visible text.
    """
    html = (
        "<html><head><title>Pencil.dev: Introducing Code on Canvas</title>"
        '<meta charset="utf-8">'
        "</head><body><p>Real body content.</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "Real body content." in result
    assert "Introducing Code on Canvas" not in result


def test_strips_link_and_meta_tags_from_body_level():
    html = (
        "<html><head>"
        '<link rel="stylesheet" href="https://example.com/email.css">'
        '<meta name="viewport" content="width=device-width">'
        "</head><body><p>Visible</p></body></html>"
    )
    result = sanitize_email_html(html)
    assert "<link" not in result.lower()
    assert "stylesheet" not in result
    assert "viewport" not in result
    assert "Visible" in result


def test_strips_xml_island_leftover_from_mso_unwrap():
    """Some templates leak ``<xml>…</xml>`` at body level (Office island).

    Even after MSO unwrap/discard, a stray ``<xml>`` block can survive. If
    left in the fragment, lxml misreads it as generic markup and drops
    surrounding content.
    """
    html = (
        "<xml><o:OfficeDocumentSettings><o:AllowPNG/></o:OfficeDocumentSettings></xml>"
        "<p>Keep me.</p>"
    )
    result = sanitize_email_html(html)
    assert "Keep me." in result
    assert "OfficeDocumentSettings" not in result
    assert "<xml" not in result.lower()


# ---------------------------------------------------------------------------
# <body> background preservation (HubSpot Netcapital #8 and #9)
# ---------------------------------------------------------------------------


def test_preserves_body_background_color_style_in_wrapper():
    html = (
        '<html><body style="background-color:#eaeaff;margin:0">'
        "<p>content</p>"
        "</body></html>"
    )
    result = sanitize_email_html(html)
    # The background-color must survive inside a wrapping element so the
    # iframe's own white body does not win.
    assert "#eaeaff" in result
    assert "background-color" in result.lower()
    assert "content" in result


def test_preserves_body_bgcolor_attribute_in_wrapper():
    html = (
        '<html><body bgcolor="#fafafa">'
        "<p>content</p>"
        "</body></html>"
    )
    result = sanitize_email_html(html)
    # Legacy bgcolor must be promoted to inline background-color so that
    # the iframe's default white background doesn't cover it.
    assert "#fafafa" in result
    assert "background-color" in result.lower()
    assert "content" in result


def test_body_without_background_is_not_wrapped_unnecessarily():
    html = "<html><body><p>hi</p></body></html>"
    result = sanitize_email_html(html)
    # No synthetic wrapper div with a style attribute if there was nothing
    # to preserve.
    assert "<p>hi</p>" in result
    assert "background-color" not in result.lower()


# ---------------------------------------------------------------------------
# MSO / non-MSO coexistence (bug #20 Medusa, bug #73 Santander Open Academy)
# ---------------------------------------------------------------------------


def test_mso_hidden_and_non_mso_revealed_do_not_duplicate_content():
    """When the template ships both an Outlook-only block AND a non-Outlook
    revealed block with the same logical content, the output must not
    contain duplicates. The Outlook block is discarded (we're not Outlook).
    """
    html = (
        '<!--[if mso]>'
        '<table><tr><td><img src="https://cdn.example.com/hero.png" alt="HERO IMAGE"></td></tr></table>'
        '<![endif]-->'
        '<!--[if !mso]><!-- -->'
        '<table><tr><td><img src="https://cdn.example.com/hero.png" alt="HERO IMAGE"></td></tr></table>'
        '<!--<![endif]-->'
    )
    result = sanitize_email_html(html)
    assert result.count('alt="HERO IMAGE"') == 1


def test_mso_xml_island_discarded_keeps_following_content():
    html = (
        '<!--[if gte mso 9]><xml>'
        '<o:OfficeDocumentSettings><o:AllowPNG/></o:OfficeDocumentSettings>'
        '</xml><![endif]-->'
        '<p>Still here.</p>'
    )
    result = sanitize_email_html(html)
    assert "Still here." in result
    # The XML content inside the hidden conditional must be gone
    assert "OfficeDocumentSettings" not in result
    assert "AllowPNG" not in result


# ---------------------------------------------------------------------------
# Resilient <style> sanitisation (preheader bugs #5, #22, #51, #73, #84, #143, #315)
# ---------------------------------------------------------------------------


def test_preheader_display_none_rule_survives_sibling_broken_rule():
    """One bad CSS rule must not wipe the whole <style> block.

    Real templates frequently mix ``.preheader{display:none}`` (keeps the
    preview text hidden) with other rules that may fail to parse under
    cssutils' strict mode. Previously, a single parse failure wiped the
    whole block and the preheader leaked as visible text.
    """
    html = (
        "<html><head><style>"
        ".broken { width: calc(100% - ); }"
        ".preheader { display: none; max-height: 0; overflow: hidden; font-size: 0; }"
        "</style></head><body>"
        '<div class="preheader">PREHEADER TEXT</div>'
        "<p>Real body.</p>"
        "</body></html>"
    )
    result = sanitize_email_html(html)
    # premailer inlines .preheader {display:none} onto the div
    assert "display:none" in result.replace(" ", "").lower()
    assert "Real body." in result


# ---------------------------------------------------------------------------
# Full-body regression — MJML / tracking pixel patterns that previously lost
# the body entirely (Pencil.dev, Artlist, Eurofirms).
# ---------------------------------------------------------------------------


def test_mjml_pattern_with_doctype_title_meta_keeps_body_content():
    """Bug #36 Pencil.dev pattern: full DOCTYPE + head + MJML-style body.

    Input comes straight from the provider API with DOCTYPE, <html>,
    <head> (with <title>, <meta>, <style>) and <body> containing the
    actual newsletter tables. Before Fix A, lxml's fragment parser
    would reorganise the leftover head-level tags into a degenerate
    tree and drop large parts of the body.
    """
    html = (
        "<!DOCTYPE html>"
        '<html lang="en"><head>'
        "<title>Newsletter subject here</title>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        "<style>.wfix{margin:0 auto;max-width:600px}</style>"
        '</head><body style="background-color:#f0f0f0">'
        '<div class="wfix">'
        "<h1>NEWSLETTER HERO</h1>"
        "<p>Este es uno GRANDE. Introducción al código en el lienzo.</p>"
        '<table><tr><td><img src="https://cdn.example.com/hero.png" width="600"></td></tr></table>'
        "<p>Keep reading for more details…</p>"
        "</div>"
        "</body></html>"
    )
    result = sanitize_email_html(html)
    # The subject MUST NOT leak into the body
    assert "Newsletter subject here" not in result
    # The MJML body content MUST survive in full
    assert "NEWSLETTER HERO" in result
    assert "Este es uno GRANDE" in result
    assert "Keep reading" in result
    assert 'src="https://cdn.example.com/hero.png"' in result


def test_tracking_pixel_does_not_replace_body():
    """Bug #56 Artlist pattern: body with visible content + 1×1 tracking pixel.

    The tracking pixel was the only surviving body element before the fix.
    """
    html = (
        "<!DOCTYPE html>"
        "<html><head><title>Marketing</title></head>"
        "<body>"
        '<div style="max-width:600px;margin:0 auto">'
        "<h1>The ultimate guide to Seedance 2.0</h1>"
        "<p>See what the new model can do in under 2 minutes.</p>"
        '<a href="https://artlist.io/read">Read more</a>'
        "</div>"
        '<img border="0" width="1" height="1" alt="" src="https://clicks.artlist.io/pixel.gif">'
        "</body></html>"
    )
    result = sanitize_email_html(html)
    assert "The ultimate guide to Seedance 2.0" in result
    assert "See what the new model can do" in result
    assert "Read more" in result
    # Tracking pixel still present but is NOT the only thing left
    assert 'src="https://clicks.artlist.io/pixel.gif"' in result


def test_head_with_font_description_does_not_leak_into_body():
    """Bug #473 Eurofirms pattern: email leaks Google Fonts README-like content.

    The input includes head-level elements that shouldn't render (the
    Quicksand description text was surviving, while the real body was
    dropped). After Fix A+D the real body content is visible.
    """
    html = (
        "<!DOCTYPE html>"
        "<html><head>"
        "<title>Mantén tu seguridad digital con Eurofirms</title>"
        '<meta charset="utf-8">'
        "</head><body>"
        "<h1>Mantén tu seguridad digital</h1>"
        "<p>Buenas prácticas de seguridad en Eurofirms.</p>"
        "<p>Activa la autenticación en dos pasos y cambia tus contraseñas regularmente.</p>"
        "</body></html>"
    )
    result = sanitize_email_html(html)
    assert "Mantén tu seguridad digital" in result
    assert "Buenas prácticas" in result
    assert "autenticación en dos pasos" in result
    # Title text doesn't leak (already in body as <h1>, but there's only 1 occurrence)
    # No mojibake
    assert "Ã" not in result


# ---------------------------------------------------------------------------
# Robustness regressions for the sixth-round pipeline hardening (this PR)
# ---------------------------------------------------------------------------


def test_body_style_with_double_quotes_inside_single_quoted_attr():
    """A single-quoted ``<body style='…"…"…'>`` triggered the bug: the old
    ``replace('"', "'")`` rewrote the inner double quotes into single ones,
    producing a wrapper div with mismatched quoting that bleach/lxml could
    misparse. After Fix 2 the attribute is HTML-escaped (``&quot;``), so the
    wrapper ``<div>`` is always well-formed and the body survives intact.
    """
    html = (
        "<html><body style='font-family:\"Helvetica Neue\",Arial,"
        "sans-serif;background-color:#eaeaff'>"
        "<p>contenido visible</p>"
        "</body></html>"
    )
    result = sanitize_email_html(html)
    assert "contenido visible" in result
    # Background must still be promoted to the wrapper div.
    assert "#eaeaff" in result
    # The original <body> tag is gone (flattened into a wrapper div).
    assert "<body" not in result.lower()
    # No half-escaped attribute leftover that would render as visible text.
    assert "font-family" in result.lower()


def test_geometry_mirror_preserves_count_when_lxml_normalises_entities():
    """lxml normalises ``&`` → ``&amp;`` and re-quotes attributes, so the
    serialised output is often *longer* than the input. Before Fix 1 the
    50%-byte guard could (in adversarial cases) trigger on innocent input.
    The new guard counts critical layout elements (img/td/th/table) before
    and after, so cosmetic byte deltas no longer matter.
    """
    html = (
        '<table width="600"><tr>'
        '<td style="width:300px"><a href="https://example.com/?a=1&amp;b=2&amp;c=3'
        '&amp;d=4&amp;e=5&amp;f=6&amp;g=7">link</a></td>'
        '<td style="height:120px"><img src="https://x.test/i.png" '
        'style="width:200px;height:80px" alt="x"></td>'
        "</tr></table>"
    )
    result = sanitize_email_html(html)
    # Geometry mirroring must apply: width/height end up as attributes.
    assert 'width="300"' in result
    assert 'height="120"' in result
    assert 'width="200"' in result
    assert 'height="80"' in result
    # Original table width must survive as well.
    assert 'width="600"' in result
