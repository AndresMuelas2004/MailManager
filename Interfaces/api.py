from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.email.email_manager import EmailManager
from core.email.gmail_client import GmailClient


app = FastAPI(title="MailApp API")


class CreateAccountRequest(BaseModel):
    account_label: str


class SendEmailRequest(BaseModel):
    from_label: str
    to: str
    subject: str
    body: str


_email_manager = EmailManager()


def _get_clients():
    return _email_manager._clients


def _find_client(label: str):
    for client in _get_clients():
        if client.get_account_label() == label:
            return client
    return None


def _email_to_dict(email):
    return {
        "account_label": email.provider,
        "message_id": email.message_id,
        "subject": email.subject,
        "sender": email.sender,
        "recipients": email.recipients,
        "body": email.body,
        "sent_at": email.sent_at.isoformat() if email.sent_at else None,
    }


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/accounts")
def create_account(request: CreateAccountRequest):
    try:
        client = GmailClient(request.account_label)
        _email_manager.add_client(client)
    except Exception as exc:
        _raise_http_error(exc)
    return {"status": "ok"}


@app.get("/accounts")
def list_accounts():
    try:
        accounts = [client.get_account_label() for client in _get_clients()]
    except Exception as exc:
        _raise_http_error(exc)
    return {"accounts": accounts}


@app.post("/accounts/{label}/authenticate")
def authenticate_account(label: str):
    try:
        client = _find_client(label)
        if client is None:
            raise ValueError(f"Account '{label}' not found.")
        client.authenticate()
    except Exception as exc:
        _raise_http_error(exc)
    return {"status": "ok"}


@app.get("/emails/unread")
def get_unread_emails():
    try:
        unread_emails = _email_manager.fetch_all_unread_emails()
        emails = [_email_to_dict(email) for email in unread_emails]
    except Exception as exc:
        _raise_http_error(exc)
    return {"emails": emails}


@app.post("/emails/send")
def send_email(request: SendEmailRequest):
    try:
        _email_manager.send_email_from_account(
            account_label=request.from_label,
            subject=request.subject,
            body=request.body,
            recipients=[request.to],
        )
    except Exception as exc:
        _raise_http_error(exc)
    return {"status": "sent"}
