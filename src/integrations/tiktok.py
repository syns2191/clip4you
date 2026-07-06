"""TikTok OAuth 2.0 — Authorization Code flow with local callback server."""

import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from .manager import ConnectedAccount, get_manager

_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_USER_URL = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name"
_SCOPES = "user.info.basic,video.publish"
_REDIRECT_PORT = 8765
_REDIRECT_URI = f"http://localhost:{_REDIRECT_PORT}/callback"


def connect(client_key: str, client_secret: str) -> ConnectedAccount:
    """Run the OAuth browser flow for TikTok. Returns the stored account."""
    if not client_key or not client_secret:
        raise ValueError("TikTok Client Key and Client Secret are required.\n"
                         "Get them at https://developers.tiktok.com/")

    state = secrets.token_urlsafe(16)
    code_holder: list[str] = []
    error_holder: list[str] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            if params.get("state") != state:
                error_holder.append("State mismatch — possible CSRF")
            elif "error" in params:
                error_holder.append(params["error"])
            else:
                code_holder.append(params.get("code", ""))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = "Connected! You can close this tab." if code_holder else f"Error: {error_holder}"
            self.wfile.write(f"<h2>{msg}</h2>".encode())

        def log_message(self, *_):
            pass

    server = HTTPServer(("localhost", _REDIRECT_PORT), _Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    auth_params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": _SCOPES,
        "redirect_uri": _REDIRECT_URI,
        "state": state,
    }
    auth_url = _AUTH_URL + "?" + urllib.parse.urlencode(auth_params)
    print(f"TikTok: opening browser for authorization...")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    if error_holder:
        raise RuntimeError(f"TikTok auth error: {error_holder[0]}")
    if not code_holder:
        raise TimeoutError("TikTok: no response within 120s — did you complete authorization in the browser?")

    code = code_holder[0]
    token_resp = requests.post(_TOKEN_URL, data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _REDIRECT_URI,
    }, timeout=30)
    token_resp.raise_for_status()
    token = token_resp.json()

    user_resp = requests.get(
        _USER_URL,
        headers={"Authorization": f"Bearer {token['access_token']}"},
        timeout=15,
    )
    user_data = user_resp.json().get("data", {}).get("user", {}) if user_resp.ok else {}
    open_id = user_data.get("open_id") or token.get("open_id", "unknown")
    display_name = user_data.get("display_name", "@tiktok_user")

    account = ConnectedAccount(
        platform="tiktok",
        account_id=open_id,
        display_name=display_name,
        token=token,
        extra={"client_key": client_key, "client_secret": client_secret},
    )
    get_manager().upsert(account)
    print(f"TikTok connected: {display_name} ({open_id})")
    return account


def refresh_token(account: ConnectedAccount) -> ConnectedAccount:
    token_resp = requests.post(_TOKEN_URL, data={
        "client_key": account.extra["client_key"],
        "client_secret": account.extra["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": account.token["refresh_token"],
    }, timeout=30)
    token_resp.raise_for_status()
    account.token = token_resp.json()
    get_manager().upsert(account)
    return account


def is_connected(account: ConnectedAccount) -> bool:
    return bool(account.token.get("access_token"))
