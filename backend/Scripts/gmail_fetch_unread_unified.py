from dataclasses import asdict
from pprint import pformat

from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


def format_email_message(email) -> str:
    data = asdict(email)
    if data.get("sent_at") is not None:
        data["sent_at"] = data["sent_at"].isoformat()

    reduced = {
        "sender": data.get("sender", ""),
        "sent_at": data.get("sent_at", ""),
        "subject": data.get("subject", ""),
        "body": data.get("body", ""),
    }
    return pformat(reduced, sort_dicts=False)


def main() -> None:
    manager = EmailManager()
    manager.add_client(GmailClient(account_label="amuelas30"))
    manager.add_client(GmailClient(account_label="muelonmuelon12"))
    manager.authenticate_all()

    unread_emails = manager.fetch_all_unread_emails()
    if not unread_emails:
        print("No hay correos no leidos.")
        return

    for index, email in enumerate(unread_emails, start=1):
        print(f"Correo {index}")
        print(format_email_message(email))
        print("")


if __name__ == "__main__":
    main()
