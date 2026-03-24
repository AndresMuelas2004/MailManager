"""Connect an account to its email provider via the API service layer."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from api.services.accounts_service import connect_account
from database import mailbox_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect an account to its email provider.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    parser.add_argument("--account-id", required=True, help="Account ID (UUID).")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Error: mailbox '{args.mailbox_id}' not found.")
        return

    result = connect_account(args.mailbox_id, args.account_id, mailbox["owner_user_id"])
    print("Account connection result:")
    for key, value in result.model_dump().items():
        print(f"  {key}: {value}")

    parametros = Path(__file__).resolve().parents[1] / "EXECUTION_MDs" / "parametros.md"
    with parametros.open("a", encoding="utf-8") as f:
        f.write(f"connect_account: mailbox={args.mailbox_id} | account={args.account_id} | connected={result.connected}\n")


if __name__ == "__main__":
    main()
