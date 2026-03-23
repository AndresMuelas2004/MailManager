"""Register a mailbox via the API service layer."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from api.schemas.mailbox import MailboxCreate
from api.services.mailboxes_service import create_mailbox


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a mailbox.")
    parser.add_argument("--user-id", required=True, help="Owner user ID (UUID).")
    parser.add_argument("--display-name", required=True, help="Mailbox display name.")
    args = parser.parse_args()

    result = create_mailbox(MailboxCreate(display_name=args.display_name), args.user_id)
    print("Mailbox registered:")
    for key, value in result.model_dump().items():
        print(f"  {key}: {value}")

    params_log = Path(__file__).resolve().parents[1] / "EXECUTION_MDs" / "parametros.md"
    with params_log.open("a", encoding="utf-8") as f:
        f.write(f"mailbox_id: {result.mailbox_id} | display_name: {result.display_name}\n")


if __name__ == "__main__":
    main()
