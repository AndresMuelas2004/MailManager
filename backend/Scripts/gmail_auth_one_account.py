from core.email.gmail_client import GmailClient


def main() -> None:
    client = GmailClient(account_label="amuelas30")
    client.authenticate()
    print("Authenticated: amuelas30")


if __name__ == "__main__":
    main()
