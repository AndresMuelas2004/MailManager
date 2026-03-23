"""Delete an account via the API service layer (cascades to emails)."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from api.services.accounts_service import delete_account
from database import mailbox_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete an account.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    parser.add_argument("--account-id", required=True, help="Account ID (UUID).")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Error: mailbox '{args.mailbox_id}' not found.")
        return

    delete_account(args.mailbox_id, args.account_id, mailbox["owner_user_id"])
    print(f"Account '{args.account_id}' deleted from mailbox '{args.mailbox_id}' (cascaded to emails).")


if __name__ == "__main__":
    main()
