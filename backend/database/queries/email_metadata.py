"""
Email metadata SQL statements.
"""

UPSERT_EMAIL_METADATA_BATCH = """
    INSERT INTO email_metadata
        (provider_message_id, account_id, thread_id, from_email, from_name,
         subject, received_at, is_read, box)
    VALUES %s
    ON CONFLICT (provider_message_id, account_id) DO UPDATE SET
        is_read = EXCLUDED.is_read,
        box     = EXCLUDED.box
"""

LIST_BY_ACCOUNT = """
    SELECT provider_message_id, account_id, thread_id, from_email, from_name,
           subject, received_at, is_read, box
    FROM email_metadata
    WHERE account_id = %(account_id)s
    ORDER BY received_at DESC
"""

DELETE_BY_ACCOUNT = """
    DELETE FROM email_metadata WHERE account_id = %(account_id)s
"""
