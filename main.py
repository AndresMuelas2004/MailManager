from core.email.gmail_client import GmailClient

def main():
    client = GmailClient()
    client.authenticate()

if __name__ == "__main__":
    main()