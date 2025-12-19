from core.email.gmail_client import GmailClient

def main():
    client = GmailClient(account_label="amuelas30")
    client.authenticate()
    client.send_email(
        subject="Prueba",
        body="Hola, esto es una prueba.",
        recipients=["amuelas30@gmail.com"],
    )
    
    unread_emails = client.fetch_unread_emails()

    print(f"Unread emails fetched: {len(unread_emails)}")

    for i, email in enumerate(unread_emails, start=1):
        print(f"\n--- Email #{i} ---")
        print(email)

if __name__ == "__main__":
    main()