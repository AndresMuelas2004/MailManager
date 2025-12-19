from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


def main() -> None:
    manager = EmailManager()
    manager.add_client(GmailClient(account_label="amuelas30"))
    manager.add_client(GmailClient(account_label="muelonmuelon12"))
    manager.authenticate_all()

    manager.send_email_from_account(
        account_label="amuelas30",
        subject="Test",
        body="Email sent from amuelas30",
        recipients=["muelonmuelon12@gmail.com"],
    )
    print("Sent from amuelas30 to muelonmuelon12")


if __name__ == "__main__":
    main()
