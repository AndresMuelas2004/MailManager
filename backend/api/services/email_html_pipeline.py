"""HTML rendering pipeline for email content.

Transforms provider-supplied HTML (Gmail MIME parts, Outlook Graph body) into
browser-safe HTML for the sandboxed iframe viewer. All functions in this module
are pure — no DB, no auth, no network. ``prepare_email_html`` is the single
entry point and composes the individual steps in the correct order.

Pipeline
--------
1. ``_normalize_charset_meta`` — strip bogus ``<meta charset>`` / ``<meta
   http-equiv>`` declarations (Outlook injects ``charset=us-ascii``) and inject
   a canonical UTF-8 meta so lxml/html5lib treat the input as UTF-8.
2. ``_unwrap_mso_conditionals`` — unwrap ``<!--[if mso | IE]>…<![endif]-->``
   and ``<!--[if !mso]>…<![endif]-->`` so the desktop layout used by Outlook
   templates survives the later comment-stripping pass.
3. ``_sanitize_style_blocks`` — parse each ``<style>`` block with cssutils,
   filter properties against the allowlist, drop unsafe at-rules (``@import``,
   ``@namespace``, ``@charset``) and keep ``@media`` / ``@supports`` /
   ``@font-face`` / style rules. Also drops property values containing
   ``expression(…)`` or ``javascript:`` schemes.
4. ``_inline_css_via_premailer`` — inline style rules into ``style=""``
   attributes for parity with mail clients that strip ``<style>`` blocks. The
   sanitized ``<style>`` block is kept (``keep_style_tags=True``) so ``@media``
   queries and pseudo-classes survive and render correctly in the iframe.
5. ``_mirror_geometry_to_attributes`` — mirror ``width``/``height`` values
   from inline styles back onto HTML attributes on ``<img>``/``<td>``/``<th>``/
   ``<table>``. Gives signature tables and inline logos a second fallback if
   the style is ever lost downstream.
6. ``_strip_script_blocks`` — remove ``<script>`` blocks entirely (content
   included). ``<style>`` is intentionally left alone now; its content was
   sanitized in step 3 and is preserved through bleach.
7. ``_clean_with_bleach`` — final tag/attribute/protocol allowlist. Inline
   ``style=""`` attributes are filtered through ``CSSSanitizer``.
"""

from __future__ import annotations

import logging
import re
from html import escape as html_escape
from typing import Any

import bleach

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowlists
# ---------------------------------------------------------------------------

_ALLOWED_TAGS: list[str] = [
    "a", "abbr", "b", "blockquote", "br", "center", "code", "dd", "del",
    "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "img", "ins", "li", "mark", "ol", "p", "pre", "q", "s",
    "small", "span", "strong", "style", "sub", "sup", "table", "tbody",
    "td", "tfoot", "th", "thead", "tr", "u", "ul", "wbr",
]

_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "*": ["class", "id", "style", "dir", "lang", "title", "align", "valign"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height", "border"],
    "td": ["colspan", "rowspan", "width", "height", "align", "valign", "bgcolor"],
    "th": ["colspan", "rowspan", "width", "height", "align", "valign", "bgcolor"],
    "table": ["border", "cellpadding", "cellspacing", "width", "align", "bgcolor"],
    "font": ["color", "size", "face"],
    "ol": ["start", "type"],
}

_ALLOWED_PROTOCOLS: list[str] = ["http", "https", "mailto", "cid", "data"]

# CSS properties safe to keep inside ``style=""`` attributes and inside
# ``<style>`` rules. Covers the vocabulary real email templates use (layout,
# colors, typography, spacing, borders) without opening the door to properties
# that pull in remote resources or execute logic.
_ALLOWED_CSS_PROPERTIES: frozenset[str] = frozenset({
    "align-items", "background", "background-color", "background-image",
    "background-position", "background-repeat", "background-size", "border",
    "border-bottom", "border-bottom-color", "border-bottom-left-radius",
    "border-bottom-right-radius", "border-bottom-style", "border-bottom-width",
    "border-collapse", "border-color", "border-left", "border-left-color",
    "border-left-style", "border-left-width", "border-radius", "border-right",
    "border-right-color", "border-right-style", "border-right-width",
    "border-spacing", "border-style", "border-top", "border-top-color",
    "border-top-left-radius", "border-top-right-radius", "border-top-style",
    "border-top-width", "border-width", "bottom", "box-shadow", "box-sizing",
    "caption-side", "clear", "color", "display", "empty-cells", "float",
    "font", "font-family", "font-size", "font-stretch", "font-style",
    "font-variant", "font-weight", "gap", "height", "justify-content", "left",
    "letter-spacing", "line-height", "list-style", "list-style-position",
    "list-style-type", "margin", "margin-bottom", "margin-left", "margin-right",
    "margin-top", "max-height", "max-width", "min-height", "min-width",
    "mso-line-height-rule", "mso-table-lspace", "mso-table-rspace", "opacity",
    "outline", "overflow", "overflow-wrap", "overflow-x", "overflow-y",
    "padding", "padding-bottom", "padding-left", "padding-right", "padding-top",
    "page-break-after", "page-break-before", "position", "right", "src",
    "table-layout", "text-align", "text-decoration", "text-indent",
    "text-overflow", "text-shadow", "text-transform", "top", "vertical-align",
    "visibility", "white-space", "width", "word-break", "word-spacing",
    "word-wrap", "z-index",
})

# At-rules kept inside ``<style>`` blocks. ``@import`` / ``@namespace`` /
# ``@charset`` are dropped (can fetch remote resources or change parsing) —
# ``@media`` and ``@supports`` carry responsive layouts and must survive.
# ``@font-face`` is kept so corporate signatures with web fonts still render.
_ALLOWED_CSS_AT_RULES: frozenset[str] = frozenset({"media", "supports", "font-face"})


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Outlook-generated HTML routinely declares a bogus charset in the <head>
# (``<meta http-equiv="Content-Type" content="…; charset=us-ascii">`` or
# ``<meta charset="windows-1252">``) that does not match the actual UTF-8
# bytes. Handing that to lxml (premailer) or html5lib (bleach) makes both
# parsers honour the wrong charset and silently re-interpret UTF-8 as
# Latin-1 — the classic ``í`` → ``Ã­`` mojibake. We strip every such meta
# and inject a canonical UTF-8 meta so both parsers agree on the encoding.
_CHARSET_META_RE = re.compile(
    r"""<meta\s+[^>]*?(?:
            charset\s*=\s*["']?[^"'>\s/]+
          | http-equiv\s*=\s*["']?content-type["']?[^>]*?content\s*=\s*["'][^"']*charset=[^"';]+
        )[^>]*>""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)

# Outlook templates wrap layout in MSO/IE conditional comments. Three
# concrete shapes show up in the wild and all three must be handled, because
# bleach's ``strip_comments=True`` would otherwise take chunks of the email
# layout with them, and a half-unwrapped comment leaves stray ``<!--`` /
# ``-->`` that derail the html5lib parser:
#
# 1. ``<!--[if mso | IE]>DESKTOP<![endif]-->`` — *downlevel-hidden*: content
#    visible only to Outlook/IE. For modern webmail we want DESKTOP to render
#    as regular markup (the alternative mobile fallback is usually a 4%-wide
#    placeholder).
# 2. ``<!--[if !mso]><!-- -->VISIBLE<!--<![endif]-->`` — *downlevel-revealed*
#    using the short form: VISIBLE is what every non-Outlook client shows.
#    The inner ``<!-- -->`` + ``<!--`` pair nullifies the outer comment for
#    standards-compliant parsers. We must strip the FULL marker including the
#    inner comment delimiters, otherwise an unpaired ``<!--`` survives.
# 3. ``<!--[if gte mso 9]><xml>…</xml><![endif]-->`` — *downlevel-hidden* XML
#    island (Office document settings). Unwrapping is safe because bleach
#    will strip ``<xml>`` / ``<o:…>`` tags downstream.
#
# The two alternatives below cover the three shapes: the first matches the
# downlevel-revealed form (captures only the inner VISIBLE content), the
# second matches the downlevel-hidden form.
_MSO_CONDITIONAL_RE = re.compile(
    r"""
    # Revealed opener matches both the standard long form
    # ``<!--[if …]><!-- -->`` (space between the inner ``<!--`` and ``-->``)
    # AND the compact short form ``<!--[if …]><!-->`` (MailChimp/HubSpot)
    # where the inner comment self-closes with a bare ``>``. Missing the
    # compact form previously let the hidden-alternative regex swallow
    # ``<!--[if !mso]>…<!--<![endif]-->`` templates and drop their payload.
    <!--\s*\[if[^\]]*\]>\s*<!--(?:\s*-->|>)
    (?P<revealed>.*?)                       # visible payload
    <!--\s*<!\[endif\]-->                   # revealed closer: <!--<![endif]-->
    |
    <!--\s*\[if[^\]]*\]>                    # hidden opener: <!--[if …]>
    (?P<hidden>.*?)                         # Outlook-only payload
    <!\[endif\]-->                          # hidden closer: <![endif]-->
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE,
)

# ``<script>`` blocks must be removed with their inner text — bleach's
# ``strip=True`` would keep their contents, which the browser would then
# execute as raw JavaScript. The alternation ``</script\s*>|\Z`` also matches
# unterminated blocks that extend to EOF, so malformed input is still handled.
_SCRIPT_BLOCK_RE = re.compile(
    r"<script\b[^>]*>.*?(?:</script\s*>|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# ``<style>`` blocks are extracted for in-place CSS sanitisation before the
# rest of the pipeline runs. Same unterminated-block tolerance as above.
_STYLE_BLOCK_RE = re.compile(
    r"(?P<open><style\b[^>]*>)(?P<body>.*?)(?P<close></style\s*>|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# Document-level wrappers are stripped after premailer so ``<style>`` blocks
# that lived in ``<head>`` become body-level fragments. Without this step,
# lxml's ``fragment_fromstring`` (used by geometry restoration) restructures
# ``<head>``/``<body>`` and drops the residual ``<style>`` block, losing the
# ``@media`` queries that mobile-first newsletters rely on.
_DOC_WRAPPER_RE = re.compile(
    r"</?(?:html|head|body)\b[^>]*>",
    re.IGNORECASE,
)

# Head-only constructs that MUST NOT remain at body-level after flattening.
# Leaving ``<title>`` would leak the subject text as visible body content
# (bleach strips the tag but keeps the inner text). Leaving ``<meta>``,
# ``<link>``, ``<base>``, ``<!DOCTYPE>`` or stray ``<xml>`` islands confuses
# lxml's fragment parser (head-only elements forced at body level reorganise
# the tree and drop surrounding content — Pencil.dev #36, Artlist #56,
# Eurofirms #473). Stripping them here gives geometry restoration and bleach
# a clean fragment to work with.
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_TITLE_BLOCK_RE = re.compile(
    r"<title\b[^>]*>.*?(?:</title\s*>|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_XML_BLOCK_RE = re.compile(
    r"<xml\b[^>]*>.*?(?:</xml\s*>|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_LINK_RE = re.compile(r"<link\b[^>]*/?>", re.IGNORECASE)
_META_RE = re.compile(r"<meta\b[^>]*/?>", re.IGNORECASE)
_BASE_RE = re.compile(r"<base\b[^>]*/?>", re.IGNORECASE)
_BODY_OPEN_RE = re.compile(r"<body\b([^>]*)>", re.IGNORECASE)
_BODY_STYLE_ATTR_RE = re.compile(
    r"""style\s*=\s*(?:"([^"]*)"|'([^']*)')""",
    re.IGNORECASE,
)
_BODY_BGCOLOR_ATTR_RE = re.compile(
    r"""bgcolor\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
    re.IGNORECASE,
)

# Premailer rewrites HTML attributes like ``width="600"`` into inline styles
# (``style="width: 600px"``) and drops the original attribute. Mirroring the
# values back onto the HTML attribute gives the layout two independent
# channels to survive the rest of the pipeline. Used by
# ``_mirror_geometry_to_attributes``.
_GEOMETRY_STYLE_RE: dict[str, re.Pattern[str]] = {
    "width": re.compile(r"(?:^|;)\s*width\s*:\s*(\d+)(?:\.\d+)?\s*px", re.IGNORECASE),
    "height": re.compile(r"(?:^|;)\s*height\s*:\s*(\d+)(?:\.\d+)?\s*px", re.IGNORECASE),
}

# Property values matching this expression are dropped from CSS (both inline
# styles and ``<style>`` blocks). Covers ``expression(…)`` (legacy IE code
# execution) and any scheme-based URL carrying JavaScript.
_UNSAFE_CSS_VALUE_RE = re.compile(
    r"(expression\s*\(|javascript\s*:|vbscript\s*:)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Step 1 — charset meta normalisation
# ---------------------------------------------------------------------------


def _normalize_charset_meta(html: str) -> str:
    """Drop any declared charset meta; inject canonical UTF-8 only inside ``<head>``.

    When the input has no ``<head>``, we deliberately skip the injection:
    prepending a ``<meta>`` before a ``<!DOCTYPE>`` would push lxml/html5lib
    into quirks mode, and a Python ``str`` already arrives Unicode-decoded —
    downstream parsers default to UTF-8 in the absence of any declaration.
    """
    html = _CHARSET_META_RE.sub("", html)
    head_open = _HEAD_OPEN_RE.search(html)
    if head_open:
        return html[: head_open.end()] + '<meta charset="utf-8">' + html[head_open.end():]
    return html


# ---------------------------------------------------------------------------
# Step 2 — MSO conditional unwrap
# ---------------------------------------------------------------------------


_MSO_DISCARD_BYTES_THRESHOLD = 200
_MSO_BODY_TEXT_THRESHOLD = 50


def _visible_text_length(html: str) -> int:
    """Rough count of visible text after stripping tags, comments and whitespace."""
    no_comments = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    no_tags = re.sub(r"<[^>]+>", "", no_comments)
    return len(re.sub(r"\s+", "", no_tags))


def _unwrap_mso_conditionals(html: str) -> str:
    """Unwrap downlevel-revealed conditionals and discard Outlook-only blocks.

    Two conditional-comment shapes appear in email templates:
      * ``<!--[if !mso]><!-- -->X<!--<![endif]-->`` — downlevel-revealed.
        ``X`` is what non-Outlook clients should see. We keep ``X`` (it IS
        our content) and drop the wrapper.
      * ``<!--[if mso | IE]>X<![endif]-->`` (also ``[if gte mso 9]``, etc.) —
        downlevel-hidden. ``X`` is Outlook-only; for web clients, ``X`` must
        stay invisible. Since the pipeline renders inside a sandboxed iframe
        (a web client, not Outlook), we discard ``X`` entirely. Unwrapping
        it caused visible duplication whenever templates shipped both a
        desktop MSO variant AND a non-MSO variant (Medusa Festival #20,
        Santander Open Academy #73).

    When discarding hidden blocks leaves an empty body, we log a warning so
    legacy MSO-only newsletters (rare but possible) become observable instead
    of silently disappearing.
    """
    discarded_bytes = 0

    def _replace(m: re.Match[str]) -> str:
        nonlocal discarded_bytes
        if m.group("revealed") is not None:
            return m.group("revealed")
        hidden = m.group("hidden") or ""
        discarded_bytes += len(hidden)
        return ""

    result = _MSO_CONDITIONAL_RE.sub(_replace, html)
    if (
        discarded_bytes > _MSO_DISCARD_BYTES_THRESHOLD
        and _visible_text_length(result) < _MSO_BODY_TEXT_THRESHOLD
    ):
        logger.warning(
            "MSO-only email detected: discarded %d bytes of Outlook-hidden "
            "content but the remaining body has < %d visible chars; "
            "consider whether the template needs special handling",
            discarded_bytes, _MSO_BODY_TEXT_THRESHOLD,
        )
    return result


# ---------------------------------------------------------------------------
# Step 3 — sanitise <style> blocks (keeps @media, @supports, @font-face)
# ---------------------------------------------------------------------------


def _sanitize_css_declarations(style: Any) -> None:
    """Strip disallowed properties and unsafe values from a CSSStyleDeclaration.

    Mutates ``style`` in place. Properties whose name is outside the allowlist
    are removed entirely; allowed properties whose value contains
    ``expression(…)`` / ``javascript:`` / ``vbscript:`` are dropped too.
    """
    for name in [p.name for p in style.getProperties(all=True)]:
        if name.lower() not in _ALLOWED_CSS_PROPERTIES:
            style.removeProperty(name)
            continue
        value = style.getPropertyValue(name) or ""
        if _UNSAFE_CSS_VALUE_RE.search(value):
            style.removeProperty(name)


def _sanitize_css_rules(rules: Any) -> None:
    """Filter a ``CSSRuleList`` in place: drop unsafe at-rules, recurse into media.

    Each rule is evaluated inside its own ``try`` so a single unparseable or
    malformed rule cannot take the whole ``<style>`` block down (previously a
    broken rule would wipe ``.preheader{display:none}`` sitting next to it,
    causing the preheader bugs #5, #22, #51, #73, #84, #143, #315).

    The at-rule decision uses ``_ALLOWED_CSS_AT_RULES`` as the single source
    of truth: if you want to drop ``@media`` in the future, remove it from
    the constant — no code change needed here.
    """
    from cssutils.css import CSSRule  # lazy — transitive dep of premailer

    # Map each cssutils rule constant to its at-rule keyword for an
    # allowlist lookup. CSSSupportsRule isn't always exposed as a constant,
    # so we fall back to a class-name check below.
    nested_at_rules: dict[int, str] = {
        CSSRule.MEDIA_RULE: "media",
        CSSRule.FONT_FACE_RULE: "font-face",
    }

    to_remove: list[Any] = []
    for rule in list(rules):
        try:
            rule_type = getattr(rule, "type", None)
            if rule_type == CSSRule.STYLE_RULE:
                _sanitize_css_declarations(rule.style)
                continue
            at_rule = nested_at_rules.get(rule_type)
            if at_rule is not None:
                if at_rule not in _ALLOWED_CSS_AT_RULES:
                    to_remove.append(rule)
                    continue
                if rule_type == CSSRule.MEDIA_RULE:
                    _sanitize_css_rules(rule.cssRules)
                else:
                    _sanitize_css_declarations(rule.style)
                continue
            if (
                type(rule).__name__ == "CSSSupportsRule"
                and "supports" in _ALLOWED_CSS_AT_RULES
            ):
                _sanitize_css_rules(rule.cssRules)
                continue
            # import, namespace, charset, page, keyframes, unknown → drop.
            to_remove.append(rule)
        except Exception as exc:
            logger.debug(
                "dropping unparseable CSS rule (%s): %s",
                type(exc).__name__, exc,
            )
            to_remove.append(rule)

    for rule in to_remove:
        try:
            rules.remove(rule)
        except Exception:
            # cssutils occasionally rejects a removal if the rule has already
            # been detached — treat as a no-op.
            pass


def _sanitize_style_blocks(html: str) -> str:
    """Sanitise every ``<style>`` block in place with cssutils.

    Keeps the ``<style>`` tag with filtered content so ``@media`` queries and
    pseudo-class rules survive and render inside the iframe. If a block fails
    to parse it is replaced with an empty ``<style>`` tag rather than dropping
    the surrounding markup — the rest of the pipeline still runs.
    """
    if "<style" not in html.lower():
        return html

    try:
        import cssutils  # lazy — transitive dep of premailer
    except Exception as exc:  # pragma: no cover — cssutils ships with premailer
        logger.warning("cssutils unavailable; dropping <style> blocks (%s): %s",
                       type(exc).__name__, exc)
        return _STYLE_BLOCK_RE.sub("", html)

    # Silence cssutils' verbose parser warnings — real emails are messy.
    cssutils.log.setLevel(logging.CRITICAL)

    def _replace(match: re.Match[str]) -> str:
        body = match.group("body")
        open_tag = match.group("open")
        close_tag = match.group("close") or "</style>"
        if not body or not body.strip():
            return f"{open_tag}{close_tag}"
        try:
            sheet = cssutils.parseString(body, validate=False)
            _sanitize_css_rules(sheet.cssRules)
            cleaned = sheet.cssText.decode("utf-8") if isinstance(sheet.cssText, bytes) else sheet.cssText
        except Exception as exc:
            logger.warning(
                "style block sanitize failed (%s): %s — dropping block",
                type(exc).__name__, exc,
            )
            return f"{open_tag}{close_tag}"
        return f"{open_tag}{cleaned}{close_tag}"

    return _STYLE_BLOCK_RE.sub(_replace, html)


# ---------------------------------------------------------------------------
# Step 4 — inline CSS via premailer
# ---------------------------------------------------------------------------


def _inline_css_via_premailer(html: str) -> str:
    """Inline style rules into ``style=""`` attrs, keep residual ``<style>`` intact."""
    try:
        from premailer import transform  # lazy — avoids startup cost
        return transform(
            html,
            keep_style_tags=True,
            remove_classes=False,
            cssutils_logging_level="CRITICAL",
            disable_validation=True,
        )
    except Exception as exc:
        logger.warning("premailer failed (%s): %s", type(exc).__name__, exc)
        return html


# ---------------------------------------------------------------------------
# Step 5a — flatten document wrappers so <style> survives lxml/bleach
# ---------------------------------------------------------------------------


def _extract_body_background(body_attrs: str) -> str:
    """Read ``style`` + ``bgcolor`` from a ``<body …>`` tag and return a
    combined CSS declaration string (e.g. ``background-color:#fafafa;margin:0``).
    Returns an empty string when the body has nothing we need to preserve.
    """
    style_match = _BODY_STYLE_ATTR_RE.search(body_attrs)
    style_value = ""
    if style_match:
        style_value = (style_match.group(1) or style_match.group(2) or "").strip()
    bgcolor_match = _BODY_BGCOLOR_ATTR_RE.search(body_attrs)
    bgcolor_value = ""
    if bgcolor_match:
        bgcolor_value = (
            bgcolor_match.group(1)
            or bgcolor_match.group(2)
            or bgcolor_match.group(3)
            or ""
        ).strip()
    parts: list[str] = []
    if bgcolor_value:
        # Promote the legacy attribute to a style so the iframe's own white
        # background cannot cover it.
        parts.append(f"background-color: {bgcolor_value}")
    if style_value:
        parts.append(style_value.rstrip(";"))
    return "; ".join(parts)


def _flatten_document_wrappers(html: str) -> str:
    """Strip head-only tags and document wrappers so the fragment is safe for
    lxml's fragment parser and bleach. When the original ``<body>`` carried a
    ``style``/``bgcolor``, wrap the resulting content in a ``<div>`` so the
    background survives the iframe's own ``body{background:#fff}`` reset.
    """
    wrap_style = ""
    body_match = _BODY_OPEN_RE.search(html)
    if body_match:
        wrap_style = _extract_body_background(body_match.group(1))

    # 1. Remove head-only blocks with their content (title leaks subject text
    #    into the body; xml islands confuse lxml's fragment parser).
    html = _DOCTYPE_RE.sub("", html)
    html = _TITLE_BLOCK_RE.sub("", html)
    html = _XML_BLOCK_RE.sub("", html)
    # 2. Remove head-only void tags.
    html = _LINK_RE.sub("", html)
    html = _META_RE.sub("", html)
    html = _BASE_RE.sub("", html)
    # 3. Remove html/head/body structural tags (not their content).
    html = _DOC_WRAPPER_RE.sub("", html)

    # 4. Re-apply the body's background inside a wrapping div so the iframe's
    #    own body{background:#fff} does not override it (HubSpot Netcapital
    #    lavender background, #8 / #9). Use html.escape(quote=True) so a
    #    style mixing single AND double quotes (e.g. font-family lists) keeps
    #    the attribute well-formed; CSSSanitizer cleans the CSS later.
    if wrap_style:
        html = f'<div style="{html_escape(wrap_style, quote=True)}">{html}</div>'

    return html


# ---------------------------------------------------------------------------
# Step 5b — mirror geometry to HTML attributes
# ---------------------------------------------------------------------------


_CRITICAL_ELEMENT_RE = re.compile(
    r"<(?:img|td|th|table)\b", re.IGNORECASE,
)


def _mirror_geometry_to_attributes(html: str) -> str:
    """Mirror ``width``/``height`` from inline styles to HTML attributes.

    Premailer rewrites ``<td width="500">`` into ``<td style="width:500px">``
    and drops the attribute. Re-asserting it as an attribute on
    ``<img>``/``<td>``/``<th>``/``<table>`` gives signature tables and inline
    logos a fallback dimension even if the style is stripped later.

    Defensive guard: count critical layout elements (``img``/``td``/``th``/
    ``table``) before and after the lxml reparse. If the post-reparse count
    is less than half the input count, lxml mis-interpreted the fragment and
    we return the original ``html`` unchanged. We deliberately do NOT
    compare byte lengths — lxml normalises entities (``&`` → ``&amp;``) and
    requotes attributes, so byte deltas trigger false positives on totally
    valid input.
    """
    try:
        from lxml import html as lxml_html  # lazy — transitive dep of premailer
    except Exception as exc:  # pragma: no cover — lxml ships with premailer
        logger.warning("lxml unavailable for geometry restoration (%s): %s",
                       type(exc).__name__, exc)
        return html
    try:
        tree = lxml_html.fragment_fromstring(html, create_parent="div")
    except Exception as exc:
        logger.warning("geometry restoration parse failed (%s): %s",
                       type(exc).__name__, exc)
        return html
    critical_before = len(_CRITICAL_ELEMENT_RE.findall(html))
    critical_after = sum(1 for _ in tree.iter("img", "td", "th", "table"))
    if critical_before > 0 and critical_after < critical_before / 2:
        logger.warning(
            "geometry restoration lost critical elements (%d → %d); "
            "returning input unchanged",
            critical_before, critical_after,
        )
        return html
    for element in tree.iter("img", "td", "th", "table"):
        style = element.get("style") or ""
        if not style:
            continue
        for attr, pattern in _GEOMETRY_STYLE_RE.items():
            if element.get(attr):
                continue
            match = pattern.search(style)
            if match:
                element.set(attr, match.group(1))
    # fragment_fromstring wraps the content in a synthetic <div>; unwrap it.
    inner = "".join(
        lxml_html.tostring(child, encoding="unicode", with_tail=True)
        for child in tree
    )
    if tree.text:
        inner = tree.text + inner
    return inner


# ---------------------------------------------------------------------------
# Step 6 — strip <script> blocks
# ---------------------------------------------------------------------------


def _strip_script_blocks(html: str) -> str:
    """Remove ``<script>`` blocks entirely (tag and inner contents)."""
    return _SCRIPT_BLOCK_RE.sub("", html)


# ---------------------------------------------------------------------------
# Step 7 — final bleach sanitization
# ---------------------------------------------------------------------------


def _clean_with_bleach(html: str) -> str:
    """Final allowlist pass: tags, attributes, protocols, inline CSS."""
    from bleach.css_sanitizer import CSSSanitizer  # lazy — optional dep
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=_ALLOWED_CSS_PROPERTIES,
        allowed_svg_properties=frozenset(),
    )
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        css_sanitizer=css_sanitizer,
        strip=True,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def prepare_email_html(html: str) -> str:
    """Transform provider HTML into browser-safe HTML for the iframe viewer.

    Runs the full pipeline (charset → MSO unwrap → <style> sanitize → CSS
    inline → geometry mirror → <script> strip → bleach). Each step is
    fail-soft: on any unexpected error the step logs a warning and returns the
    input unchanged, so bleach always sees well-formed content and no step can
    take down the endpoint.
    """
    if not html or html.isspace():
        return html
    html = _normalize_charset_meta(html)
    html = _unwrap_mso_conditionals(html)
    html = _sanitize_style_blocks(html)
    html = _inline_css_via_premailer(html)
    html = _flatten_document_wrappers(html)
    html = _mirror_geometry_to_attributes(html)
    html = _strip_script_blocks(html)
    return _clean_with_bleach(html)
