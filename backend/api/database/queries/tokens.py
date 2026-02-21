"""
Token SQL statements.
"""

SELECT_TOKENS_BY_CONTEXT = """
    SELECT
        t.account_id,
        t.access_token,
        t.refresh_token,
        t.access_token_encrypted,
        t.refresh_token_encrypted,
        t.encryption_key_id,
        t.expiry,
        t.scopes
    FROM tokens AS t
    JOIN accounts AS a
      ON a.account_id = t.account_id
    WHERE a.account_id = %(account_id)s
      AND a.mailbox_id = %(mailbox_id)s
      AND a.provider = %(provider)s
"""

UPSERT_TOKENS_ENCRYPTED = """
    INSERT INTO tokens (
        account_id,
        access_token,
        refresh_token,
        access_token_encrypted,
        refresh_token_encrypted,
        encryption_key_id,
        expiry,
        scopes,
        updated_at
    )
    SELECT
        a.account_id,
        NULL,
        NULL,
        %(access_token_encrypted)s,
        %(refresh_token_encrypted)s,
        %(encryption_key_id)s,
        %(expiry)s,
        %(scopes)s,
        now()
    FROM accounts AS a
    WHERE a.account_id = %(account_id)s
      AND a.mailbox_id = %(mailbox_id)s
      AND a.provider = %(provider)s
    ON CONFLICT (account_id) DO UPDATE SET
        access_token = NULL,
        refresh_token = NULL,
        access_token_encrypted = EXCLUDED.access_token_encrypted,
        refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
        encryption_key_id = EXCLUDED.encryption_key_id,
        expiry = EXCLUDED.expiry,
        scopes = EXCLUDED.scopes,
        updated_at = now()
"""

UPSERT_TOKENS_PLAINTEXT = """
    INSERT INTO tokens (
        account_id,
        access_token,
        refresh_token,
        access_token_encrypted,
        refresh_token_encrypted,
        encryption_key_id,
        expiry,
        scopes,
        updated_at
    )
    SELECT
        a.account_id,
        %(access_token)s,
        %(refresh_token)s,
        NULL,
        NULL,
        NULL,
        %(expiry)s,
        %(scopes)s,
        now()
    FROM accounts AS a
    WHERE a.account_id = %(account_id)s
      AND a.mailbox_id = %(mailbox_id)s
      AND a.provider = %(provider)s
    ON CONFLICT (account_id) DO UPDATE SET
        access_token = EXCLUDED.access_token,
        refresh_token = EXCLUDED.refresh_token,
        access_token_encrypted = NULL,
        refresh_token_encrypted = NULL,
        encryption_key_id = NULL,
        expiry = EXCLUDED.expiry,
        scopes = EXCLUDED.scopes,
        updated_at = now()
"""

BACKFILL_LEGACY_TOKENS = """
    UPDATE tokens AS t
       SET access_token = NULL,
           refresh_token = NULL,
           access_token_encrypted = %(access_token_encrypted)s,
           refresh_token_encrypted = %(refresh_token_encrypted)s,
           encryption_key_id = %(encryption_key_id)s,
           updated_at = now()
      FROM accounts AS a
     WHERE t.account_id = a.account_id
       AND a.account_id = %(account_id)s
       AND a.mailbox_id = %(mailbox_id)s
       AND a.provider = %(provider)s
"""

DELETE_TOKENS_BY_ACCOUNT_IDS = """
    DELETE FROM tokens
    WHERE account_id = ANY(%s)
"""
