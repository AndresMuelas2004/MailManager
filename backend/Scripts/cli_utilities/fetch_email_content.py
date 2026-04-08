"""Fetch the full content of a specific email by message ID."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import mailbox_store
from api.services.emails_service import get_email_full_content


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch full email content for a specific message.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    parser.add_argument("--account-id", required=True, help="Account ID (UUID).")
    parser.add_argument("--message-id", required=True, help="Provider message ID.")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Mailbox '{args.mailbox_id}' not found.")
        return

    owner_user_id = mailbox["owner_user_id"]
    print(f"Fetching content for message '{args.message_id}' "
          f"(account '{args.account_id}', mailbox '{args.mailbox_id}')...")

    result = get_email_full_content(args.mailbox_id, args.message_id, args.account_id, owner_user_id)
    print(result)


if __name__ == "__main__":
    main()
