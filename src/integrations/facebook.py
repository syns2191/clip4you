"""Facebook OAuth 2.0 — Authorization Code flow with local callback server."""

import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from .manager import ConnectedAccount, get_manager

_AUTH_URL       = "https://www.facebook.com/v19.0/dialog/oauth"
_TOKEN_URL      = "https://graph.facebook.com/v19.0/oauth/access_token"
_LONG_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
_PAGES_URL      = "https://graph.facebook.com/v19.0/me/accounts"
_REDIRECT_PORT  = 8766
_REDIRECT_URI   = f"http://localhost:{_REDIRECT_PORT}/callback"
_SCOPES         = "pages_manage_posts,pages_read_engagement,pages_show_list"


def connect(app_id: str, app_secret: str) -> list[ConnectedAccount]:
    """Run the OAuth browser flow. Returns a list of connected Page accounts."""
    if not app_id or not app_secret:
        raise ValueError("Facebook App ID and App Secret are required.\n"
                         "Get them at https://developers.facebook.com/")

    state = secrets.token_urlsafe(16)
    code_holder: list[str] = []
    error_holder: list[str] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            if params.get("state") != state:
                error_holder.append("State mismatch")
            elif "error" in params:
                error_holder.append(params.get("error_description", params["error"]))
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

    auth_url = _AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": app_id,
        "redirect_uri": _REDIRECT_URI,
        "scope": _SCOPES,
        "state": state,
        "response_type": "code",
    })
    print("Facebook: opening browser for authorization...")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    if error_holder:
        raise RuntimeError(f"Facebook auth error: {error_holder[0]}")
    if not code_holder:
        raise TimeoutError("Facebook: no response within 120s")

    # Exchange code for short-lived user token
    token_resp = requests.get(_TOKEN_URL, params={
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": _REDIRECT_URI,
        "code": code_holder[0],
    }, timeout=30)
    token_resp.raise_for_status()
    short_token = token_resp.json()["access_token"]

    # Exchange for long-lived token (~60 days)
    long_resp = requests.get(_LONG_TOKEN_URL, params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    }, timeout=30)
    long_resp.raise_for_status()
    long_token = long_resp.json()["access_token"]

    # Fetch managed Pages — each becomes a separate account
    pages_resp = requests.get(_PAGES_URL, params={
        "access_token": long_token,
        "fields": "id,name,access_token",
    }, timeout=30)
    pages_resp.raise_for_status()
    pages = pages_resp.json().get("data", [])

    accounts = []
    for page in pages:
        account = ConnectedAccount(
            platform="facebook",
            account_id=page["id"],
            display_name=page["name"],
            token={"access_token": page["access_token"]},
            extra={"app_id": app_id, "app_secret": app_secret},
        )
        get_manager().upsert(account)
        print(f"Facebook page connected: {page['name']} ({page['id']})")
        accounts.append(account)

    if not accounts:
        me_resp = requests.get("https://graph.facebook.com/v19.0/me",
                               params={"access_token": long_token}, timeout=15)
        me = me_resp.json() if me_resp.ok else {}
        account = ConnectedAccount(
            platform="facebook",
            account_id=me.get("id", "unknown"),
            display_name=me.get("name", "Facebook User"),
            token={"access_token": long_token},
            extra={"app_id": app_id, "app_secret": app_secret},
        )
        get_manager().upsert(account)
        accounts.append(account)

    return accounts


def is_connected(account: ConnectedAccount) -> bool:
    return bool(account.token.get("access_token"))
