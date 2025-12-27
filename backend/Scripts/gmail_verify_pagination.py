from core.email.gmail_client import GmailClient


PAGE_SIZE = 25
MAX_TOTAL = PAGE_SIZE * 3
MIN_TOTAL = PAGE_SIZE + 1


def main() -> None:
    client = GmailClient(account_label="amuelas30")
    client.authenticate()

    emails = client.fetch_unread_emails(max_total=MAX_TOTAL, page_size=PAGE_SIZE)
    total = len(emails)

    if total < MIN_TOTAL:
        print(
            "Not enough unread emails to verify pagination. "
            f"Need at least {MIN_TOTAL}, got {total}."
        )
        return

    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 0

    print(f"Total obtenidos: {total}")
    print(f"Paginas estimadas: {pages}")
    if emails:
        print(f"Primer message_id: {emails[0].message_id}")
        print(f"Ultimo message_id: {emails[-1].message_id}")


if __name__ == "__main__":
    main()
