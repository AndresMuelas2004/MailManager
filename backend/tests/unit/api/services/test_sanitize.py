"""
Unit tests for sanitize_email_html.
"""

from __future__ import annotations

from api.services.services_helpers import sanitize_email_html


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


def test_empty_string_returns_empty():
    assert sanitize_email_html("") == ""


def test_whitespace_returns_as_is():
    assert sanitize_email_html("   ") == "   "


def test_strips_onerror_on_img():
    html = '<img src="x" onerror="alert(1)">'
    result = sanitize_email_html(html)
    assert "onerror" not in result
    assert "<img " in result


def test_inlines_style_tag_into_attributes():
    html = "<html><head><style>p{color:red}</style></head><body><p>hi</p></body></html>"
    result = sanitize_email_html(html)
    assert "<style>" not in result
    assert "</style>" not in result
    # premailer inlines the rule onto the <p> tag
    assert "color:red" in result.replace(" ", "")


def test_inlines_class_selectors():
    html = (
        "<html><head><style>.btn{background:#1a73e8;color:#fff}</style></head>"
        "<body><a class=\"btn\" href=\"https://example.com\">click</a></body></html>"
    )
    result = sanitize_email_html(html)
    assert "<style>" not in result
    normalized = result.replace(" ", "").lower()
    assert "background:#1a73e8" in normalized
    assert "color:#fff" in normalized


def test_strips_dangerous_css_url():
    html = (
        "<html><head><style>a{background:url(javascript:alert(1))}</style></head>"
        "<body><a href=\"https://example.com\">x</a></body></html>"
    )
    result = sanitize_email_html(html)
    assert "javascript:" not in result


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
