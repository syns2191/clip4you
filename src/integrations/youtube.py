"""YouTube OAuth — wraps the existing google-auth flow."""

import json
import os

from .manager import ConnectedAccount, get_manager

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def connect(client_secrets_path: str = "") -> ConnectedAccount:
    """Run the OAuth browser flow and store the resulting token. Returns the account."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    path = client_secrets_path.strip() or os.path.join(_ROOT, "client_secret.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"client_secret.json not found at: {path}\n"
            "Go to https://console.cloud.google.com/ → YouTube Data API v3 → OAuth 2.0 credentials."
        )

    # Remove any cached token — scopes may have changed
    token_cache = os.path.join(_ROOT, ".youtube_token.json")
    if os.path.exists(token_cache):
        os.remove(token_cache)

    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    creds = flow.run_local_server(port=0)

    # Fetch channel info to get a display name
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    channel_id = items[0]["id"] if items else "unknown"
    channel_name = items[0]["snippet"]["title"] if items else "My Channel"

    account = ConnectedAccount(
        platform="youtube",
        account_id=channel_id,
        display_name=channel_name,
        token=json.loads(creds.to_json()),
        extra={"client_secrets_path": path},
    )
    get_manager().upsert(account)
    print(f"YouTube connected: {channel_name} ({channel_id})")
    return account


def get_service(account: ConnectedAccount):
    """Return an authenticated YouTube API service for the given account."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_info(account.token, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        account.token = json.loads(creds.to_json())
        get_manager().upsert(account)

    return build("youtube", "v3", credentials=creds)


def is_connected(account: ConnectedAccount) -> bool:
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_info(account.token, SCOPES)
        return creds.valid or bool(creds.refresh_token)
    except Exception:
        return False
