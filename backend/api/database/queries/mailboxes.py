"""
Mailbox SQL statements.
"""

INSERT_MAILBOX = """
    INSERT INTO mailboxes (mailbox_id, display_name, owner_user_id)
    VALUES (%(mailbox_id)s, %(display_name)s, %(owner_user_id)s)
    RETURNING mailbox_id, display_name, owner_user_id, created_at
"""

LIST_MAILBOXES_BY_OWNER = """
    SELECT mailbox_id, display_name, owner_user_id, created_at
    FROM mailboxes
    WHERE owner_user_id = %(owner_user_id)s
    ORDER BY created_at
"""

GET_MAILBOX = """
    SELECT mailbox_id, display_name, owner_user_id, created_at
    FROM mailboxes
    WHERE mailbox_id = %(mailbox_id)s
"""

DELETE_MAILBOX = """
    DELETE FROM mailboxes
    WHERE mailbox_id = %(mailbox_id)s
"""

