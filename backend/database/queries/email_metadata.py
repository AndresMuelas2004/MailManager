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
        box = CASE
            WHEN email_metadata.box = 'DELETED' AND EXCLUDED.box = 'TRASH'
            THEN 'DELETED'
            ELSE EXCLUDED.box
        END
"""

LIST_BY_ACCOUNT = """
    SELECT provider_message_id, account_id, thread_id, from_email, from_name,
           subject, received_at, is_read, box
    FROM email_metadata
    WHERE account_id = %(account_id)s AND box != 'DELETED'
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
           box = CASE
               WHEN em.box = 'DELETED' AND v.box = 'TRASH'
               THEN 'DELETED'
               ELSE v.box
           END
      FROM (VALUES %s) AS v(provider_message_id, account_id, is_read, box)
     WHERE em.provider_message_id = v.provider_message_id::VARCHAR
       AND em.account_id          = v.account_id::UUID
"""

LIST_PROVIDER_MESSAGE_IDS_BY_ACCOUNT = """
    SELECT provider_message_id
    FROM email_metadata
    WHERE account_id = %(account_id)s
"""

GET_TRASH_EMAILS_BY_IDS = """
    SELECT provider_message_id, account_id, box, previous_box
    FROM email_metadata
    WHERE account_id = %(account_id)s
      AND provider_message_id = ANY(%(message_ids)s)
      AND box = 'TRASH'
"""

MARK_AS_DELETED_BATCH = """
    UPDATE email_metadata
    SET box = 'DELETED'
    WHERE account_id = %(account_id)s
      AND provider_message_id = ANY(%(message_ids)s)
      AND box = 'TRASH'
"""

RESTORE_FROM_TRASH_BATCH = """
    UPDATE email_metadata AS em
    SET provider_message_id = v.new_message_id::VARCHAR,
        box = COALESCE(em.previous_box, 'ALL_MAIL'),
        previous_box = NULL
    FROM (VALUES %s) AS v(old_message_id, new_message_id, account_id)
    WHERE em.provider_message_id = v.old_message_id::VARCHAR
      AND em.account_id = v.account_id::UUID
      AND em.box = 'TRASH'
"""

RESTORE_FROM_TRASH_DISCOVERED_BATCH = """
    UPDATE email_metadata AS em
    SET provider_message_id = v.new_message_id::VARCHAR,
        box = v.discovered_box::VARCHAR,
        previous_box = NULL
    FROM (VALUES %s) AS v(old_message_id, new_message_id, account_id, discovered_box)
    WHERE em.provider_message_id = v.old_message_id::VARCHAR
      AND em.account_id = v.account_id::UUID
      AND em.box = 'TRASH'
"""

MOVE_TO_TRASH_BATCH = """
    UPDATE email_metadata AS em
    SET provider_message_id = v.new_message_id::VARCHAR,
        previous_box = em.box,
        box = 'TRASH'
    FROM (VALUES %s) AS v(old_message_id, new_message_id, account_id)
    WHERE em.provider_message_id = v.old_message_id::VARCHAR
      AND em.account_id = v.account_id::UUID
      AND em.box NOT IN ('TRASH', 'DELETED')
"""
