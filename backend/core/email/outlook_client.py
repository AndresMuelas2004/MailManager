from __future__ import annotations

from typing import List

from .email_client import EmailClient, EmailMessage


class OutlookClient(EmailClient):
    """
    Concrete implementation of EmailClient for Outlook accounts.
    This class will be responsible for talking to Microsoft Graph API.
    """

    def __init__(
        self,
        account_label: str,
        client_id: str,
        client_secret: str,
        tenant_id: str,
    ) -> None:
        """
        :param account_label: Human-readable label for this Outlook account.
        :param client_id: Application client ID for Microsoft Graph.
        :param client_secret: Application client secret for Microsoft Graph.
        :param tenant_id: Directory (tenant) ID for Microsoft Graph.
        """
        self._account_label = account_label
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id
        self._graph_client = None  # Will hold the Graph API client instance

    def authenticate(self) -> None:
        """
        Initialize or refresh the Microsoft Graph client using OAuth2.
        """
        # TODO: Implement OAuth2 authentication for Microsoft Graph API.
        raise NotImplementedError("OutlookClient.authenticate() not implemented yet.")

    def fetch_unread_emails(self) -> List[EmailMessage]:
        """
        Fetch unread Outlook messages, normalize them into EmailMessage objects
        and return them as a list.
        """
        # TODO: Call Microsoft Graph to list unread messages
        #       and map them into EmailMessage instances.
        raise NotImplementedError("OutlookClient.fetch_unread_emails() not implemented yet.")

    def send_email(
        self,
        subject: str,
        body: str,
        recipients: List[str],
    ) -> None:
        """
        Send a plain text email using Microsoft Graph API.
        """
        # TODO: Build the message payload and send it through Microsoft Graph.
        raise NotImplementedError("OutlookClient.send_email() not implemented yet.")

    def get_account_label(self) -> str:
        """
        Return the label that identifies this Outlook account inside the app.
        """
        return self._account_label