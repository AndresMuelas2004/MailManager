"""E2E test configuration — pre-existing test account identifiers."""
from __future__ import annotations

import os

TEST_USER_ID       = os.getenv("E2E_TEST_USER_ID",       "1be0fffd-7490-4969-aa3d-98cbfb35f045")
GMAIL_MAILBOX_ID   = os.getenv("E2E_GMAIL_MAILBOX_ID",   "28a83414-36f5-4115-ab61-977d5a06a8e1")
OUTLOOK_MAILBOX_ID = os.getenv("E2E_OUTLOOK_MAILBOX_ID", "b61e15d5-153e-42ee-a4c6-2c943bd13c07")
GMAIL_ACCOUNT_ID   = os.getenv("E2E_GMAIL_ACCOUNT_ID",   "9805b672-032b-4d74-9696-4db53a5eb512")
OUTLOOK_ACCOUNT_ID = os.getenv("E2E_OUTLOOK_ACCOUNT_ID", "3c55eb17-9d5e-4d31-a3b5-14c6c24279b9")
SEND_RECIPIENT     = os.getenv("E2E_SEND_RECIPIENT",     "muelonmuelon12@gmail.com")
