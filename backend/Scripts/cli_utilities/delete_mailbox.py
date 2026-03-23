"""Delete a mailbox via the API service layer (cascades to accounts and emails)."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from api.services.mailboxes_service import delete_mailbox
from database import mailbox_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete a mailbox.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Error: mailbox '{args.mailbox_id}' not found.")
        return

    delete_mailbox(args.mailbox_id, mailbox["owner_user_id"])
    print(f"Mailbox '{args.mailbox_id}' deleted (cascaded to accounts and emails).")


if __name__ == "__main__":
    main()
