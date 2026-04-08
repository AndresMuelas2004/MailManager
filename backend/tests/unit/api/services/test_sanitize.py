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


def test_strips_style_tag():
    html = "<style>body{color:red}</style>"
    result = sanitize_email_html(html)
    assert "<style>" not in result
    assert "</style>" not in result
