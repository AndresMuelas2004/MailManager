"""Fetch and sync email metadata for all accounts under a mailbox."""
from __future__ import annotations
import logging; logging.basicConfig(level=logging.DEBUG, format='%(name)s %(message)s')
import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import mailbox_store
from api.services.emails_service import sync_email_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch email metadata for a mailbox.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Mailbox '{args.mailbox_id}' not found.")
        return

    owner_user_id = mailbox["owner_user_id"]
    print(f"Syncing metadata for mailbox '{args.mailbox_id}' (owner: {owner_user_id})...")

    result = sync_email_metadata(args.mailbox_id, owner_user_id)
    print(f"Total synced: {result.total_synced}")
    for detail in result.accounts:
        print(f"  account_id: {detail.account_id}, provider: {detail.provider}, "
              f"emails_synced: {detail.emails_synced}, sync_cursor: {detail.sync_cursor}")


if __name__ == "__main__":
    main()
