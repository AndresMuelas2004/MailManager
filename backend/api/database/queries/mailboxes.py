"""
Mailbox SQL statements.
"""

INSERT_MAILBOX = """
    INSERT INTO mailboxes (mailbox_id, display_name)
    VALUES (%(mailbox_id)s, %(display_name)s)
    RETURNING mailbox_id, display_name, created_at
"""

LIST_MAILBOXES = """
    SELECT mailbox_id, display_name, created_at
    FROM mailboxes
    ORDER BY created_at
"""

GET_MAILBOX = """
    SELECT mailbox_id, display_name, created_at
    FROM mailboxes
    WHERE mailbox_id = %(mailbox_id)s
"""

DELETE_MAILBOX = """
    DELETE FROM mailboxes
    WHERE mailbox_id = %(mailbox_id)s
"""

