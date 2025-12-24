import base64

from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


REQUIRED_HEADERS = ("from:", "subject:", "date:", "content-type:")


def decode_raw(raw_b64url: str) -> str:
    raw_bytes = base64.urlsafe_b64decode(raw_b64url.encode("utf-8"))
    return raw_bytes.decode("utf-8", errors="replace")


def get_header_block(raw_text: str) -> str:
    lines = raw_text.splitlines()
    header_lines = []
    for line in lines:
        if line == "":
            break
        header_lines.append(line)
    return "\n".join(header_lines)


def main() -> None:
    manager = EmailManager()
    manager.add_client(GmailClient(account_label="amuelas30"))
    manager.add_client(GmailClient(account_label="muelonmuelon12"))
    manager.authenticate_all()

    unread_emails = manager.fetch_all_unread_emails()
    if not unread_emails:
        print("No hay correos no leidos para verificar.")
        return

    for index, email in enumerate(unread_emails, start=1):
        print(f"Correo {index}")
        raw_b64url = email.raw_rfc822_b64url
        if not raw_b64url:
            print("  raw_rfc822_b64url: MISSING")
            continue

        raw_b64url = raw_b64url.strip()
        try:
            raw_text = decode_raw(raw_b64url)
        except Exception as exc:
            print(f"  raw_rfc822_b64url: ERROR al decodificar ({exc})")
            continue

        header_block = get_header_block(raw_text)
        header_block_lower = header_block.lower()
        missing = [h for h in REQUIRED_HEADERS if h not in header_block_lower]
        if missing:
            print("  Headers faltantes:", ", ".join(missing))
        else:
            print("  OK: headers basicos presentes")
        print("")


if __name__ == "__main__":
    main()
