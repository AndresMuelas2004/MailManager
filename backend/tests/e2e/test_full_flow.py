"""
E2E full-flow test — real Gmail and Outlook APIs, no fakes.

Each endpoint is its own test method inside a single class. pytest executes
methods in definition order, and shared IDs are stored in a class-level dict
so later steps can reference resources created by earlier ones.

Run with:  python -m pytest backend/tests/e2e/test_full_flow.py -v -s
"""

from __future__ import annotations

import pytest


class TestFullFlow:
    """Sequential E2E flow — one test per endpoint call."""

    state: dict[str, str] = {}

    def test_01_create_mailbox(self, e2e_client):
        r = e2e_client.post("/mailboxes", json={"display_name": "E2E Mailbox"})
        assert r.status_code == 200
        self.state["mid"] = r.json()["mailbox_id"]

    def test_02_create_gmail_account(self, e2e_client):
        base = f"/mailboxes/{self.state['mid']}/accounts"
        r = e2e_client.post(base, json={
            "provider": "gmail",
            "display_label": "prueba 1",
        })
        assert r.status_code == 200
        self.state["gmail_id"] = r.json()["account_id"]

    def test_03_create_outlook_account(self, e2e_client):
        base = f"/mailboxes/{self.state['mid']}/accounts"
        r = e2e_client.post(base, json={
            "provider": "outlook",
            "display_label": "prueba 2",
        })
        assert r.status_code == 200
        self.state["outlook_id"] = r.json()["account_id"]

    def test_04_connect_gmail(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.post(f"/mailboxes/{mid}/accounts/{self.state['gmail_id']}/connect")
        assert r.status_code == 200

    def test_05_connect_outlook(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.post(f"/mailboxes/{mid}/accounts/{self.state['outlook_id']}/connect")
        assert r.status_code == 200

    def test_06_update_gmail_label(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.patch(
            f"/mailboxes/{mid}/accounts/{self.state['gmail_id']}",
            json={"display_label": "prueba 1"},
        )
        assert r.status_code == 200

    def test_07_send_email_gmail(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.post(f"/mailboxes/{mid}/emails/send", json={
            "account_id": self.state["gmail_id"],
            "subject": "Prueba desde correo prueba 1 en test flujo completo E2E",
            "body": "E2E test — gmail account",
            "recipients": ["muelonmuelon12@gmail.com"],
        })
        assert r.status_code == 200

    def test_08_send_email_outlook(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.post(f"/mailboxes/{mid}/emails/send", json={
            "account_id": self.state["outlook_id"],
            "subject": "Prueba desde correo prueba 2 en test flujo completo E2E",
            "body": "E2E test — outlook account",
            "recipients": ["muelonmuelon12@gmail.com"],
        })
        assert r.status_code == 200

    def test_09_fetch_unread_emails(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.get(f"/mailboxes/{mid}/emails/unread")
        assert r.status_code == 200

    def test_10_list_accounts(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.get(f"/mailboxes/{mid}/accounts")
        assert r.status_code == 200

    def test_11_get_gmail_account(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.get(f"/mailboxes/{mid}/accounts/{self.state['gmail_id']}")
        assert r.status_code == 200

    def test_12_delete_outlook_account(self, e2e_client):
        mid = self.state["mid"]
        r = e2e_client.delete(f"/mailboxes/{mid}/accounts/{self.state['outlook_id']}")
        assert r.status_code == 200

    def test_13_list_mailboxes(self, e2e_client):
        r = e2e_client.get("/mailboxes")
        assert r.status_code == 200

    def test_14_get_mailbox(self, e2e_client):
        r = e2e_client.get(f"/mailboxes/{self.state['mid']}")
        assert r.status_code == 200

    def test_15_delete_mailbox(self, e2e_client):
        r = e2e_client.delete(f"/mailboxes/{self.state['mid']}")
        assert r.status_code == 200

    def test_16_verify_mailbox_gone(self, e2e_client):
        r = e2e_client.get(f"/mailboxes/{self.state['mid']}")
        assert r.status_code == 404
