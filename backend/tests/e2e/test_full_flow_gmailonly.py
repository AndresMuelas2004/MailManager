"""
E2E full-flow tests - Gmail-only variant, no Outlook.

The flow is split into one test per endpoint so pytest output shows
exactly which endpoint failed first. After the first failure, the
remaining flow tests are skipped to avoid cascade errors.

Run with: python -m pytest backend/tests/e2e/test_full_flow_gmailonly.py -v -s
"""

from __future__ import annotations

import pytest


def _assert_ok(response, *, expected: int = 200) -> None:
    assert response.status_code == expected, response.text


@pytest.fixture(scope="module")
def flow_state() -> dict[str, str]:
    return {}


@pytest.fixture(scope="module")
def flow_control() -> dict[str, str | None]:
    return {"failed_test": None}


@pytest.fixture
def run_flow_step(flow_control, request):
    failed_test = flow_control["failed_test"]
    if failed_test:
        pytest.skip(f"Skipped because '{failed_test}' failed.")

    def _run(step_fn) -> None:
        try:
            step_fn()
        except pytest.skip.Exception:
            raise
        except Exception:
            flow_control["failed_test"] = request.node.name
            raise

    return _run


# ------------------------------------------------------------------
# Auth — login
# ------------------------------------------------------------------

def test_01_post_auth_google_login(e2e_client, flow_state, run_flow_step, google_id_token):
    def _step():
        response = e2e_client.post("/auth/google", json={"id_token": google_id_token})
        _assert_ok(response)
        data = response.json()
        assert data["message"] == "Login successful."
        flow_state["user_id"] = data["user"]["user_id"]

    run_flow_step(_step)


def test_02_get_auth_me(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.get("/auth/me")
        _assert_ok(response)
        assert response.json()["user_id"] == flow_state["user_id"]

    run_flow_step(_step)


# ------------------------------------------------------------------
# Mailboxes, accounts, emails — Gmail-only flow
# ------------------------------------------------------------------

def test_03_post_mailboxes_create_mailbox(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.post("/mailboxes", json={"display_name": "E2E Mailbox"})
        _assert_ok(response)
        flow_state["mid"] = response.json()["mailbox_id"]

    run_flow_step(_step)


def test_04_post_accounts_create_gmail(
    e2e_client, flow_state, run_flow_step
):
    def _step():
        accounts_base = f"/mailboxes/{flow_state['mid']}/accounts"

        response = e2e_client.post(
            accounts_base,
            json={"provider": "gmail", "display_label": "prueba 1"},
        )
        _assert_ok(response)
        flow_state["gmail_id"] = response.json()["account_id"]

    run_flow_step(_step)


def test_05_post_connect_connect_gmail(
    e2e_client, flow_state, run_flow_step
):
    def _step():
        response = e2e_client.post(
            f"/mailboxes/{flow_state['mid']}/accounts/{flow_state['gmail_id']}/connect"
        )
        assert response.status_code == 200, (
            f"Gmail connect failed. Response: {response.text}"
        )

    run_flow_step(_step)


def test_06_patch_account_update_gmail_label(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.patch(
            f"/mailboxes/{flow_state['mid']}/accounts/{flow_state['gmail_id']}",
            json={"display_label": "prueba 1"},
        )
        _assert_ok(response)

    run_flow_step(_step)


def test_07_post_emails_send_from_gmail(
    e2e_client, flow_state, run_flow_step
):
    def _step():
        response = e2e_client.post(
            f"/mailboxes/{flow_state['mid']}/emails/send",
            json={
                "account_id": flow_state["gmail_id"],
                "subject": "Prueba desde correo prueba 1 en test flujo completo E2E",
                "body": "E2E test - gmail account",
                "recipients": ["muelonmuelon12@gmail.com"],
            },
        )
        _assert_ok(response)

    run_flow_step(_step)


def test_08_post_sync_email_metadata(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.post(f"/mailboxes/{flow_state['mid']}/emails/sync-metadata")
        _assert_ok(response)
        data = response.json()

        assert isinstance(data["total_synced"], int)
        assert data["total_synced"] >= 10

        accounts = data["accounts"]
        assert len(accounts) == 1, f"Expected 1 account, got {len(accounts)}"

        synced_ids = {a["account_id"] for a in accounts}
        assert flow_state["gmail_id"] in synced_ids

        for account in accounts:
            assert isinstance(account["emails_synced"], int)
            assert account["emails_synced"] >= 10
            assert account["provider"] == "gmail"
            assert isinstance(account["sync_cursor"], str) or account["sync_cursor"] is None

    run_flow_step(_step)


def test_08b_pause_for_db_inspection(flow_state, run_flow_step):
    def _step():
        from database import connection as conn_module

        with conn_module.get_connection() as conn:
            conn.commit()
            input(
                "\n>>> Data committed — inspect the DB in DBeaver."
                "\n>>> Press Enter to continue tests (cleanup runs at the end)... "
            )

    run_flow_step(_step)


def test_09_get_accounts_list(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.get(f"/mailboxes/{flow_state['mid']}/accounts")
        _assert_ok(response)

    run_flow_step(_step)


def test_10_get_gmail_account_detail(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.get(
            f"/mailboxes/{flow_state['mid']}/accounts/{flow_state['gmail_id']}"
        )
        _assert_ok(response)

    run_flow_step(_step)


def test_11_get_mailboxes_list(e2e_client, run_flow_step):
    def _step():
        response = e2e_client.get("/mailboxes")
        _assert_ok(response)

    run_flow_step(_step)


def test_12_get_mailbox_detail(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.get(f"/mailboxes/{flow_state['mid']}")
        _assert_ok(response)

    run_flow_step(_step)


def test_13_delete_mailbox(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.delete(f"/mailboxes/{flow_state['mid']}")
        _assert_ok(response)

    run_flow_step(_step)


def test_14_get_deleted_mailbox_returns_404(e2e_client, flow_state, run_flow_step):
    def _step():
        response = e2e_client.get(f"/mailboxes/{flow_state['mid']}")
        _assert_ok(response, expected=404)

    run_flow_step(_step)


# ------------------------------------------------------------------
# Auth — logout, re-login, delete account
# ------------------------------------------------------------------

def test_15_post_auth_logout(e2e_client, run_flow_step):
    def _step():
        response = e2e_client.post("/auth/logout")
        _assert_ok(response)
        assert response.json() == {"status": "logged_out"}

    run_flow_step(_step)


def test_16_post_auth_google_relogin(e2e_client, flow_state, run_flow_step, google_id_token):
    def _step():
        response = e2e_client.post("/auth/google", json={"id_token": google_id_token})
        _assert_ok(response)
        flow_state["user_id"] = response.json()["user"]["user_id"]

    run_flow_step(_step)


def test_17_delete_auth_me(e2e_client, run_flow_step):
    def _step():
        response = e2e_client.delete("/auth/me")
        _assert_ok(response)
        assert response.json() == {"status": "account_deleted"}

    run_flow_step(_step)


def test_18_get_auth_me_after_delete(e2e_client, run_flow_step):
    def _step():
        response = e2e_client.get("/auth/me")
        _assert_ok(response, expected=401)

    run_flow_step(_step)


def test_99_cleanup_committed_data(flow_state):
    """Delete the test user (cascade) and commit, so no orphan data remains."""
    from database import connection as conn_module

    with conn_module.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM users WHERE user_id = %s",
                (flow_state["user_id"],),
            )
        conn.commit()
