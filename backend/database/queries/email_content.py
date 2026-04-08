"""
SQL queries for email content persistence (business-logic only).
"""
from __future__ import annotations

GET_BY_MESSAGE_ID = """
    SELECT html_body, text_body, fetched_at
    FROM email_content
    WHERE provider_message_id = %(provider_message_id)s
      AND account_id = %(account_id)s
"""

UPSERT_EMAIL_CONTENT = """
    INSERT INTO email_content
        (provider_message_id, account_id, html_body, text_body)
    VALUES (%(provider_message_id)s, %(account_id)s, %(html_body)s, %(text_body)s)
    ON CONFLICT (provider_message_id, account_id) DO UPDATE SET
        html_body = EXCLUDED.html_body,
        text_body = EXCLUDED.text_body,
        fetched_at = now()
"""
