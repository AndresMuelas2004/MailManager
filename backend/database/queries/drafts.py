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

LIST_DRAFTS_BY_ACCOUNT = """
    SELECT provider_draft_id, account_id, to_recipients, cc_recipients, bcc_recipients,
           subject, body_html, created_at, updated_at
    FROM drafts
    WHERE account_id = %(account_id)s
    ORDER BY created_at DESC
"""

LIST_DRAFTS_BY_MAILBOX = """
    SELECT d.provider_draft_id, d.account_id, d.to_recipients, d.cc_recipients, d.bcc_recipients,
           d.subject, d.body_html, d.created_at, d.updated_at
    FROM drafts d
    JOIN accounts a ON d.account_id = a.account_id
    WHERE a.mailbox_id = %(mailbox_id)s
    ORDER BY d.created_at DESC
"""
