from core.email.gmail_client import GmailClient

def main():
    client = GmailClient(account_label="test_gmail")
    client.authenticate()

    unread_emails = client.fetch_unread_emails()

    print(f"Unread emails fetched: {len(unread_emails)}")

    for i, email in enumerate(unread_emails, start=1):
        print(f"\n--- Email #{i} ---")
        print(email)

if __name__ == "__main__":
    main()