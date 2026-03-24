"""
Email metadata SQL statements.
"""

from __future__ import annotations

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

DELETE_BATCH_BY_MESSAGE_IDS = """
    DELETE FROM email_metadata
    WHERE account_id = %(account_id)s
      AND provider_message_id = ANY(%(message_ids)s)
"""

UPDATE_LABELS_BATCH = """
    UPDATE email_metadata AS em
       SET is_read = v.is_read,
           box     = v.box
      FROM (VALUES %s) AS v(provider_message_id, account_id, is_read, box)
     WHERE em.provider_message_id = v.provider_message_id::VARCHAR
       AND em.account_id          = v.account_id::UUID
"""

UPDATE_READ_STATUS_BATCH = """
    UPDATE email_metadata AS em
       SET is_read = v.is_read
      FROM (VALUES %s) AS v(provider_message_id, account_id, is_read)
     WHERE em.provider_message_id = v.provider_message_id::VARCHAR
       AND em.account_id          = v.account_id::UUID
"""

UPDATE_SPAM_STATUS_BATCH = """
    UPDATE email_metadata AS em
       SET provider_message_id = v.new_message_id,
           box                 = v.new_box
      FROM (VALUES %s) AS v(old_message_id, account_id, new_message_id, new_box)
     WHERE em.provider_message_id = v.old_message_id::VARCHAR
       AND em.account_id          = v.account_id::UUID
"""

LIST_PROVIDER_MESSAGE_IDS_BY_ACCOUNT = """
    SELECT provider_message_id
    FROM email_metadata
    WHERE account_id = %(account_id)s
"""
