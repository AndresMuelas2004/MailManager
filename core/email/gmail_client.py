from __future__ import annotations

from typing import List

from .email_client import EmailClient, EmailMessage


class GmailClient(EmailClient):
    """
    Concrete implementation of EmailClient for Gmail accounts.
    This class will be responsible for talking to the official Gmail API.
    """

    def __init__(
        self,
        account_label: str,
        credentials_path: str,
        token_path: str,
    ) -> None:
        """
        :param account_label: Human-readable label for this Gmail account.
        :param credentials_path: Path to the OAuth2 client credentials file.
        :param token_path: Path where the user access token will be stored.
        """
        self._account_label = account_label
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._service = None  # Will hold the Gmail API service client

    def authenticate(self) -> None:
        """
        Initialize or refresh the Gmail API client using OAuth2.
        This method will be implemented using the Google client libraries.
        """
        # TODO: Implement OAuth2 flow and create the Gmail service instance.
        #       For now, we keep this as a placeholder.
        raise NotImplementedError("GmailClient.authenticate() not implemented yet.")

    def fetch_unread_emails(self) -> List[EmailMessage]:
        """
        Fetch unread Gmail messages, normalize them into EmailMessage objects
        and return them as a list.
        """
        # TODO: Call the Gmail API to list unread messages,
        #       then transform them into EmailMessage instances.
        raise NotImplementedError("GmailClient.fetch_unread_emails() not implemented yet.")

    def send_email(
        self,
        subject: str,
        body: str,
        recipients: List[str],
    ) -> None:
        """
        Send a plain text email using the Gmail API.
        """
        # TODO: Build a MIME message and send it via the Gmail API.
        raise NotImplementedError("GmailClient.send_email() not implemented yet.")

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Gmail account inside the app.
        """
        return self._account_label