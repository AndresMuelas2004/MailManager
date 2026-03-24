"""Delete permanently or restore emails from trash."""
from __future__ import annotations
import logging; logging.basicConfig(level=logging.DEBUG, format='%(name)s %(message)s')
import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import mailbox_store
from api.schemas.email import TrashActionRequest, TrashItem
from api.services.emails_service import manage_trash


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete permanently or restore emails from trash.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    parser.add_argument("--account-id", required=True, help="Account ID (UUID) within the mailbox.")
    parser.add_argument("--action", required=True, choices=["delete", "restore"],
                        help="Action to perform: 'delete' (permanent) or 'restore'.")
    parser.add_argument("--message-ids", required=True,
                        help="Comma-separated provider message IDs.")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Mailbox '{args.mailbox_id}' not found.")
        return

    owner_user_id = mailbox["owner_user_id"]
    message_ids = [mid.strip() for mid in args.message_ids.split(",")]

    items = [TrashItem(provider_message_id=mid, account_id=args.account_id) for mid in message_ids]
    payload = TrashActionRequest(action=args.action, items=items)

    action_label = "Deleting permanently" if args.action == "delete" else "Restoring"
    print(f"{action_label} {len(items)} email(s) for account '{args.account_id}' "
          f"in mailbox '{args.mailbox_id}'...")
    result = manage_trash(args.mailbox_id, payload, owner_user_id)
    print(f"Done. Affected: {result.affected}")


if __name__ == "__main__":
    main()
