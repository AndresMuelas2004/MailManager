from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


def main() -> None:
    manager = EmailManager()
    manager.add_client(GmailClient(account_label="amuelas30"))
    manager.add_client(GmailClient(account_label="muelonmuelon12"))
    manager.authenticate_all()

    unread_emails = manager.fetch_all_unread_emails()
    print(f"Unread emails: {len(unread_emails)}")


if __name__ == "__main__":
    main()
