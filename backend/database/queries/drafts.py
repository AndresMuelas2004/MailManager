"""
SQL queries for draft persistence (business-logic only).
"""
from __future__ import annotations

INSERT_DRAFT = """
    INSERT INTO drafts (
        provider_draft_id,
        account_id,
        to_recipients,
        cc_recipients,
        bcc_recipients,
        subject,
        body_html
    )
    VALUES (
        %(provider_draft_id)s,
        %(account_id)s,
        %(to_recipients)s,
        %(cc_recipients)s,
        %(bcc_recipients)s,
        %(subject)s,
        %(body_html)s
    )
    RETURNING
        provider_draft_id,
        account_id,
        to_recipients,
        cc_recipients,
        bcc_recipients,
        subject,
        body_html,
        created_at,
        updated_at
"""
