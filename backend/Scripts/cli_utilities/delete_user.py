"""Delete a user (cascades to mailboxes, accounts, and emails)."""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import user_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete a user.")
    parser.add_argument("--user-id", required=True, help="User ID (UUID).")
    args = parser.parse_args()

    deleted = user_store.delete(args.user_id)
    if deleted:
        print(f"User '{args.user_id}' deleted (cascaded to mailboxes, accounts, and emails).")
    else:
        print(f"User '{args.user_id}' not found.")


if __name__ == "__main__":
    main()
