"""Delete all email metadata for every account under a mailbox."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import account_store, email_metadata_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete all emails under a mailbox.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    args = parser.parse_args()

    accounts = account_store.list_by_mailbox(args.mailbox_id)
    if not accounts:
        print(f"No accounts found for mailbox '{args.mailbox_id}'.")
        return

    for account in accounts:
        account_id = account["account_id"]
        email_metadata_store.delete_by_account(account_id)
        account_store.update_sync_cursor(args.mailbox_id, account_id, None)
        print(f"  Deleted emails and reset sync cursor for account '{account_id}'.")

    print(f"Done. Cleared emails and reset sync cursors for {len(accounts)} account(s).")


if __name__ == "__main__":
    main()
