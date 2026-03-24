"""Register a user via Google OAuth interactive login."""
from __future__ import annotations

import json
import os
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from database import user_store

REDIRECT_PORT = 8085
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
SCOPES = ["openid", "email", "profile"]


def _load_google_credentials() -> tuple[str, str]:
    """Load client_id and client_secret from the Gmail credentials JSON file."""
    path = os.getenv("MIA_GMAIL_CREDENTIALS_PATH", "").strip()
    if not path:
        raise SystemExit("MIA_GMAIL_CREDENTIALS_PATH is not set in .env")

    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    creds = data.get("installed") or data.get("web") or data
    client_id = creds.get("client_id", "")
    client_secret = creds.get("client_secret", "")
    if not client_id or not client_secret:
        raise SystemExit(f"client_id or client_secret missing in {path}")
    return client_id, client_secret


def _build_auth_url(client_id: str) -> str:
    """Build the Google OAuth consent URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def _exchange_code(code: str, client_id: str, client_secret: str) -> dict:
    """Exchange the authorization code for tokens and return the id_token claims."""
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    userinfo_resp = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=10,
    )
    userinfo_resp.raise_for_status()
    return userinfo_resp.json()


def main() -> None:
    client_id, client_secret = _load_google_credentials()

    auth_code: list[str | None] = [None]

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            code = query.get("code", [None])[0]
            if code:
                auth_code[0] = code
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Login successful. You can close this tab.</h2>")
            else:
                error = query.get("error", ["unknown"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<h2>Login failed: {error}</h2>".encode())

        def log_message(self, format, *args):
            pass

    auth_url = _build_auth_url(client_id)
    print(f"Opening browser for Google login...")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    server.handle_request()

    if not auth_code[0]:
        raise SystemExit("No authorization code received.")

    print("Exchanging code for user info...")
    userinfo = _exchange_code(auth_code[0], client_id, client_secret)

    google_sub = userinfo.get("sub", "")
    email = userinfo.get("email", "")
    name = userinfo.get("name", "")
    avatar_url = userinfo.get("picture")

    if not google_sub or not email:
        raise SystemExit(f"Missing required fields in Google response: {userinfo}")

    user_id = str(uuid.uuid4())
    result = user_store.upsert({
        "user_id": user_id,
        "google_sub": google_sub,
        "email": email,
        "name": name,
        "avatar_url": avatar_url,
    })
    print("User registered:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    params_log = Path(__file__).resolve().parents[1] / "EXECUTION_MDs" / "parametros.md"
    with params_log.open("a", encoding="utf-8") as f:
        f.write(f"user_id: {result['user_id']}\n")


if __name__ == "__main__":
    main()
