"""
Concrete repository exports.
"""

from database.repositories.account_repository import account_store
from database.repositories.email_metadata_repository import email_metadata_store
from database.repositories.mailbox_repository import mailbox_store
from database.repositories.session_repository import session_store
from database.repositories.user_repository import user_store

__all__ = [
    "account_store",
    "email_metadata_store",
    "mailbox_store",
    "session_store",
    "user_store",
]
