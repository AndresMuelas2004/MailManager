"""Delete cached email content from the database."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database.connection import get_connection

_DELETE_CONTENT_BY_MESSAGE = """
    DELETE FROM email_content
    WHERE provider_message_id = %(provider_message_id)s
      AND account_id = %(account_id)s
"""

_DELETE_CONTENT_BY_ACCOUNT = """
    DELETE FROM email_content
    WHERE account_id = %(account_id)s
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete cached email content.")
    parser.add_argument("--account-id", required=True, help="Account ID (UUID).")
    parser.add_argument("--message-id", default=None, help="Provider message ID. Omit to use --all-account.")
    parser.add_argument("--all-account", action="store_true", help="Delete all content for the account.")
    args = parser.parse_args()

    if not args.message_id and not args.all_account:
        parser.error("Provide either --message-id or --all-account.")

    if args.all_account:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_DELETE_CONTENT_BY_ACCOUNT, {"account_id": args.account_id})
                deleted = cur.rowcount
        print(f"Deleted {deleted} content row(s) for account '{args.account_id}'.")
    else:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_DELETE_CONTENT_BY_MESSAGE, {
                    "provider_message_id": args.message_id,
                    "account_id": args.account_id,
                })
                deleted = cur.rowcount
        print(f"Deleted {deleted} content row(s) for message '{args.message_id}' "
              f"(account '{args.account_id}').")


if __name__ == "__main__":
    main()
