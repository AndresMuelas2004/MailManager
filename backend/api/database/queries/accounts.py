"""
Account SQL statements.
"""

LIST_ACCOUNTS_BY_MAILBOX = """
    SELECT account_id, mailbox_id, provider, display_label, config, created_at
    FROM accounts
    WHERE mailbox_id = %(mailbox_id)s
    ORDER BY created_at
"""

GET_ACCOUNT = """
    SELECT account_id, mailbox_id, provider, display_label, config, created_at
    FROM accounts
    WHERE mailbox_id = %(mailbox_id)s AND account_id = %(account_id)s
"""

UPSERT_ACCOUNT = """
    INSERT INTO accounts (account_id, mailbox_id, provider, display_label, config)
    VALUES (%(account_id)s, %(mailbox_id)s, %(provider)s, %(display_label)s, %(config)s::jsonb)
    ON CONFLICT (account_id) DO UPDATE SET
        display_label = EXCLUDED.display_label,
        config = EXCLUDED.config
    RETURNING account_id, mailbox_id, provider, display_label, config, created_at
"""

DELETE_ACCOUNT = """
    DELETE FROM accounts
    WHERE mailbox_id = %(mailbox_id)s AND account_id = %(account_id)s
"""

