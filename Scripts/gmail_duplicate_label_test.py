from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


def main() -> None:
    manager = EmailManager()
    manager.add_client(GmailClient(account_label="dup_label"))

    try:
        manager.add_client(GmailClient(account_label="dup_label"))
    except ValueError as exc:
        print(f"OK: duplicate label blocked ({exc})")
        return

    raise AssertionError("Expected ValueError for duplicate account_label, but none was raised.")


if __name__ == "__main__":
    main()
