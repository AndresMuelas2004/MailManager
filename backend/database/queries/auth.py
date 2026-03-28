"""
SQL statements for users and sessions.
"""

from __future__ import annotations

UPSERT_USER = """
    INSERT INTO users (user_id, google_sub, email, name, avatar_url)
    VALUES (%(user_id)s, %(google_sub)s, %(email)s, %(name)s, %(avatar_url)s)
    ON CONFLICT (google_sub) DO UPDATE
        SET email      = EXCLUDED.email,
            name       = EXCLUDED.name,
            avatar_url = EXCLUDED.avatar_url
    RETURNING user_id, google_sub, email, name, avatar_url, created_at
"""

GET_USER_BY_ID = """
    SELECT user_id, google_sub, email, name, avatar_url, created_at
    FROM users
    WHERE user_id = %(user_id)s
"""

INSERT_SESSION = """
    INSERT INTO sessions (session_id, user_id, expires_at)
    VALUES (%(session_id)s, %(user_id)s, %(expires_at)s)
    RETURNING session_id, user_id, expires_at, created_at
"""

GET_VALID_SESSION = """
    SELECT session_id, user_id, expires_at, created_at
    FROM sessions
    WHERE session_id = %(session_id)s
      AND expires_at > now()
"""

DELETE_SESSION = """
    DELETE FROM sessions
    WHERE session_id = %(session_id)s
"""

DELETE_EXPIRED_SESSIONS = """
    DELETE FROM sessions
    WHERE expires_at <= now()
"""

DELETE_USER = """
    DELETE FROM users
    WHERE user_id = %(user_id)s
"""
