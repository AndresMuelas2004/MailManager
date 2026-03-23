"""Send an email from a specific account under a mailbox."""
from __future__ import annotations
import logging; logging.basicConfig(level=logging.DEBUG, format='%(name)s %(message)s')
import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import mailbox_store
from api.schemas.email import EmailSendRequest
from api.services.emails_service import send_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Send an email from a mailbox account.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    parser.add_argument("--account-id", required=True, help="Account ID (UUID) within the mailbox.")
    parser.add_argument("--subject", required=True, help="Email subject.")
    parser.add_argument("--body", required=True, help="Email body text.")
    parser.add_argument("--recipients", required=True, help="Comma-separated list of recipient emails.")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Mailbox '{args.mailbox_id}' not found.")
        return

    owner_user_id = mailbox["owner_user_id"]
    recipients = [r.strip() for r in args.recipients.split(",")]

    payload = EmailSendRequest(
        account_id=args.account_id,
        subject=args.subject,
        body=args.body,
        recipients=recipients,
    )

    print(f"Sending email from account '{args.account_id}' in mailbox '{args.mailbox_id}'...")
    result = send_email(args.mailbox_id, payload, owner_user_id)
    print(f"Email sent successfully: {result}")


if __name__ == "__main__":
    main()
