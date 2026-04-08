"""
Account SQL statements.
"""

from __future__ import annotations

LIST_ACCOUNTS_BY_MAILBOX = """
    SELECT account_id, mailbox_id, provider, display_label, config, email_address, created_at
    FROM accounts
    WHERE mailbox_id = %(mailbox_id)s
    ORDER BY created_at
"""

GET_ACCOUNT = """
    SELECT account_id, mailbox_id, provider, display_label, config, email_address, created_at
    FROM accounts
    WHERE mailbox_id = %(mailbox_id)s AND account_id = %(account_id)s
"""

UPSERT_ACCOUNT = """
    INSERT INTO accounts (account_id, mailbox_id, provider, display_label, config)
    VALUES (%(account_id)s, %(mailbox_id)s, %(provider)s, %(display_label)s, %(config)s::jsonb)
    ON CONFLICT (account_id) DO UPDATE SET
        display_label = EXCLUDED.display_label,
        config = EXCLUDED.config
    RETURNING account_id, mailbox_id, provider, display_label, config, email_address, created_at
"""

DELETE_ACCOUNT = """
    DELETE FROM accounts
    WHERE mailbox_id = %(mailbox_id)s AND account_id = %(account_id)s
"""

# ---------------------------------------------------------------------------
# Token operations (columns live in accounts since migration 0005)
# ---------------------------------------------------------------------------

SELECT_TOKENS_BY_CONTEXT = """
    SELECT
        account_id,
        access_token,
        refresh_token,
        access_token_encrypted,
        refresh_token_encrypted,
        encryption_key_id,
        expiry,
        scopes
    FROM accounts
    WHERE account_id = %(account_id)s
      AND mailbox_id = %(mailbox_id)s
      AND provider = %(provider)s
"""

UPSERT_TOKENS_ENCRYPTED = """
    UPDATE accounts
       SET access_token = NULL,
           refresh_token = NULL,
           access_token_encrypted = %(access_token_encrypted)s,
           refresh_token_encrypted = %(refresh_token_encrypted)s,
           encryption_key_id = %(encryption_key_id)s,
           expiry = %(expiry)s,
           scopes = %(scopes)s,
           email_address = COALESCE(%(email_address)s, email_address),
           tokens_updated_at = now()
     WHERE account_id = %(account_id)s
       AND mailbox_id = %(mailbox_id)s
       AND provider = %(provider)s
"""

UPSERT_TOKENS_PLAINTEXT = """
    UPDATE accounts
       SET access_token = %(access_token)s,
           refresh_token = %(refresh_token)s,
           access_token_encrypted = NULL,
           refresh_token_encrypted = NULL,
           encryption_key_id = NULL,
           expiry = %(expiry)s,
           scopes = %(scopes)s,
           email_address = COALESCE(%(email_address)s, email_address),
           tokens_updated_at = now()
     WHERE account_id = %(account_id)s
       AND mailbox_id = %(mailbox_id)s
       AND provider = %(provider)s
"""

BACKFILL_LEGACY_TOKENS = """
    UPDATE accounts
       SET access_token = NULL,
           refresh_token = NULL,
           access_token_encrypted = %(access_token_encrypted)s,
           refresh_token_encrypted = %(refresh_token_encrypted)s,
           encryption_key_id = %(encryption_key_id)s,
           tokens_updated_at = now()
     WHERE account_id = %(account_id)s
       AND mailbox_id = %(mailbox_id)s
       AND provider = %(provider)s
"""

# ---------------------------------------------------------------------------
# Sync cursor operations
# ---------------------------------------------------------------------------

GET_SYNC_CURSOR = """
    SELECT sync_cursor FROM accounts
    WHERE account_id = %(account_id)s AND mailbox_id = %(mailbox_id)s
"""

UPDATE_SYNC_CURSOR = """
    UPDATE accounts SET sync_cursor = %(sync_cursor)s
    WHERE account_id = %(account_id)s AND mailbox_id = %(mailbox_id)s
"""

