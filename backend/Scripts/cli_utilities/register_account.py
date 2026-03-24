"""Register an account via the API service layer."""
from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from api.schemas.account import AccountCreate
from api.services.accounts_service import create_account
from database import mailbox_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Register an account.")
    parser.add_argument("--mailbox-id", required=True, help="Mailbox ID (UUID).")
    parser.add_argument("--provider", required=True, choices=["gmail", "outlook"], help="Email provider.")
    parser.add_argument("--display-label", default=None, help="Optional display label.")
    args = parser.parse_args()

    mailbox = mailbox_store.get(args.mailbox_id)
    if mailbox is None:
        print(f"Error: mailbox '{args.mailbox_id}' not found.")
        return

    display_label = args.display_label or f"{args.provider}:{uuid4()}"
    payload = AccountCreate(provider=args.provider, display_label=display_label, config={})
    result = create_account(args.mailbox_id, payload, mailbox["owner_user_id"])
    print("Account registered:")
    for key, value in result.model_dump().items():
        print(f"  {key}: {value}")

    params_log = Path(__file__).resolve().parents[1] / "EXECUTION_MDs" / "parametros.md"
    with params_log.open("a", encoding="utf-8") as f:
        f.write(f"account_id: {result.account_id} | provider: {result.provider} | display_label: {result.display_label}\n")


if __name__ == "__main__":
    main()
