"""Integrations tab — connect social platform accounts."""

import gradio as gr

from ...integrations.manager import ConnectedAccount, get_manager


def _status_md(accounts: list) -> str:
    if not accounts:
        return "_No accounts connected._"
    return "\n".join(f"- **{a.display_name}** `{a.account_id}`" for a in accounts)


def _choices(accounts: list) -> list[str]:
    return [f"{a.display_name} ({a.account_id})" for a in accounts]


def create_integrations_tab():
    manager = get_manager()

    gr.Markdown("Connect your social accounts. Tokens are stored locally in `integrations.json`.")

    # ── YouTube ───────────────────────────────────────────────────────────────
    with gr.Accordion("YouTube", open=True):
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown(
                    "Download `client_secret.json` from "
                    "[Google Cloud Console](https://console.cloud.google.com/) "
                    "→ YouTube Data API v3 → OAuth 2.0 credentials (Desktop app)."
                )
                yt_secrets = gr.Textbox(
                    label="client_secret.json path",
                    placeholder="client_secret.json",
                    value="client_secret.json",
                )
                yt_connect_btn = gr.Button("Connect via OAuth", variant="primary")
                yt_msg = gr.Markdown("")
            with gr.Column(scale=3):
                yt_status = gr.Markdown(_status_md(manager.for_platform("youtube")))
                yt_disconnect = gr.Dropdown(
                    label="Disconnect account",
                    choices=_choices(manager.for_platform("youtube")), value=None,
                )
                yt_disconnect_btn = gr.Button("Disconnect", size="sm", variant="stop")

    # ── TikTok ────────────────────────────────────────────────────────────────
    with gr.Accordion("TikTok", open=False):
        with gr.Row():
            with gr.Column(scale=2):
                tt_method = gr.Radio(
                    label="Connection method", choices=["OAuth", "Manual token"], value="OAuth",
                )
                with gr.Group() as tt_oauth_group:
                    gr.Markdown(
                        "Create an app at [developers.tiktok.com](https://developers.tiktok.com/) "
                        "with `video.publish` + `user.info.basic` scopes."
                    )
                    tt_client_key = gr.Textbox(label="Client Key", placeholder="tiktok_client_key...")
                    tt_client_secret = gr.Textbox(label="Client Secret", type="password", placeholder="tiktok_client_secret...")
                with gr.Group(visible=False) as tt_manual_group:
                    gr.Markdown(
                        "Go to your TikTok Developer app → **Manage app → Token generator** "
                        "to generate an access token."
                    )
                    tt_manual_token = gr.Textbox(label="Access Token", type="password", placeholder="act.xxx...")
                    tt_manual_open_id = gr.Textbox(label="Open ID", placeholder="Your TikTok open_id")
                    tt_manual_name = gr.Textbox(label="Display name", placeholder="@myaccount")
                tt_connect_btn = gr.Button("Connect TikTok Account", variant="primary")
                tt_msg = gr.Markdown("")
            with gr.Column(scale=3):
                tt_status = gr.Markdown(_status_md(manager.for_platform("tiktok")))
                tt_disconnect = gr.Dropdown(
                    label="Disconnect account",
                    choices=_choices(manager.for_platform("tiktok")), value=None,
                )
                tt_disconnect_btn = gr.Button("Disconnect", size="sm", variant="stop")

    # ── Facebook ──────────────────────────────────────────────────────────────
    with gr.Accordion("Facebook", open=False):
        with gr.Row():
            with gr.Column(scale=2):
                fb_method = gr.Radio(
                    label="Connection method", choices=["OAuth", "Manual token"], value="OAuth",
                )
                with gr.Group() as fb_oauth_group:
                    gr.Markdown(
                        "Create an app at [developers.facebook.com](https://developers.facebook.com/) "
                        "with `pages_manage_posts` + `pages_read_engagement` permissions. "
                        "Add `http://localhost:8766/callback` as a Valid OAuth Redirect URI in "
                        "**Facebook Login → Settings**."
                    )
                    fb_app_id = gr.Textbox(label="App ID", placeholder="1234567890")
                    fb_app_secret = gr.Textbox(label="App Secret", type="password", placeholder="abc123...")
                    fb_connect_btn = gr.Button("Connect via OAuth", variant="primary")
                with gr.Group(visible=False) as fb_manual_group:
                    gr.Markdown("""**How to get a Page Access Token manually:**

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Top-right dropdown → select your **App**
3. Click **Generate Access Token** → log in → add permissions:
   `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`
4. Click the token type dropdown (shows "User Token") → switch to **Page Token** → select your Page
5. Copy the token — starts with `EAA...`

**Page ID:** open your Facebook Page → **About** → scroll to the very bottom.

> Extend to 60 days: paste token in [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/) → **Extend Access Token**.""")
                    fb_manual_token = gr.Textbox(label="Page Access Token", type="password", placeholder="EAAxxxxxxx...")
                    fb_manual_page_id = gr.Textbox(label="Page ID", placeholder="123456789")
                    fb_manual_name = gr.Textbox(label="Page name", placeholder="My Page")
                    fb_manual_save_btn = gr.Button("Save Account", variant="primary")
                fb_msg = gr.Markdown("")
            with gr.Column(scale=3):
                fb_status = gr.Markdown(_status_md(manager.for_platform("facebook")))
                fb_disconnect = gr.Dropdown(
                    label="Disconnect account",
                    choices=_choices(manager.for_platform("facebook")), value=None,
                )
                fb_disconnect_btn = gr.Button("Disconnect", size="sm", variant="stop")

    # ── Instagram ─────────────────────────────────────────────────────────────
    with gr.Accordion("Instagram", open=False):
        with gr.Row():
            with gr.Column(scale=2):
                ig_method = gr.Radio(
                    label="Connection method", choices=["OAuth", "Manual token"], value="OAuth",
                )
                with gr.Group() as ig_oauth_group:
                    gr.Markdown(
                        "Uses the same Facebook App — add `instagram_basic` + `instagram_content_publish` permissions. "
                        "Add `http://localhost:8767/callback` as a Valid OAuth Redirect URI. "
                        "Instagram must be a **Business or Creator** account linked to a Facebook Page."
                    )
                    ig_app_id = gr.Textbox(label="App ID", placeholder="1234567890")
                    ig_app_secret = gr.Textbox(label="App Secret", type="password", placeholder="abc123...")
                    ig_connect_btn = gr.Button("Connect via OAuth", variant="primary")
                with gr.Group(visible=False) as ig_manual_group:
                    gr.Markdown("""**How to get an Instagram Access Token manually:**

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your **App** → **Generate Access Token** → add:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`
3. Switch token type → **Page Token** → select the Facebook Page linked to your Instagram
4. Copy the token (`EAA...`)

**Instagram Account ID:** in Graph API Explorer run:
`GET /me/accounts` → copy your page ID → then
`GET /{page-id}?fields=instagram_business_account` → copy the `id`

**Linked Facebook Page ID:** the `id` field from `/me/accounts` next to your page name.""")
                    ig_manual_token = gr.Textbox(label="Access Token", type="password", placeholder="EAAxxxxxxx...")
                    ig_manual_account_id = gr.Textbox(label="Instagram Account ID", placeholder="17841400000000000")
                    ig_manual_page_id = gr.Textbox(label="Linked Facebook Page ID", placeholder="123456789")
                    ig_manual_name = gr.Textbox(label="Display name", placeholder="@myaccount")
                    ig_manual_save_btn = gr.Button("Save Account", variant="primary")
                ig_msg = gr.Markdown("")
            with gr.Column(scale=3):
                ig_status = gr.Markdown(_status_md(manager.for_platform("instagram")))
                ig_disconnect = gr.Dropdown(
                    label="Disconnect account",
                    choices=_choices(manager.for_platform("instagram")), value=None,
                )
                ig_disconnect_btn = gr.Button("Disconnect", size="sm", variant="stop")

    # ── Method toggles ────────────────────────────────────────────────────────

    tt_method.change(
        lambda m: (gr.update(visible=m == "OAuth"), gr.update(visible=m == "Manual token")),
        [tt_method], [tt_oauth_group, tt_manual_group],
    )
    fb_method.change(
        lambda m: (gr.update(visible=m == "OAuth"), gr.update(visible=m == "Manual token")),
        [fb_method], [fb_oauth_group, fb_manual_group],
    )
    ig_method.change(
        lambda m: (gr.update(visible=m == "OAuth"), gr.update(visible=m == "Manual token")),
        [ig_method], [ig_oauth_group, ig_manual_group],
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh(platform):
        accts = manager.for_platform(platform)
        return _status_md(accts), gr.update(choices=_choices(accts), value=None)

    def _disconnect(platform, choice):
        if not choice:
            return gr.update(), gr.update()
        account_id = choice.rsplit("(", 1)[-1].rstrip(")")
        manager.remove(platform, account_id)
        return _refresh(platform)

    # ── YouTube ───────────────────────────────────────────────────────────────

    def _connect_youtube(secrets_path):
        from ...integrations import youtube as yt_mod
        try:
            yt_mod.connect(secrets_path)
            return *_refresh("youtube"), ""
        except Exception as e:
            return gr.update(), gr.update(), f"**Error:** {e}"

    yt_connect_btn.click(_connect_youtube, [yt_secrets], [yt_status, yt_disconnect, yt_msg])

    # ── TikTok ────────────────────────────────────────────────────────────────

    def _connect_tiktok(method, key, secret, token, open_id, name):
        try:
            if method == "OAuth":
                from ...integrations import tiktok as tt_mod
                tt_mod.connect(key, secret)
            else:
                if not token or not open_id:
                    return gr.update(), gr.update(), "**Access Token and Open ID are required.**"
                manager.upsert(ConnectedAccount(
                    platform="tiktok",
                    account_id=open_id.strip(),
                    display_name=name.strip() or open_id.strip(),
                    token={"access_token": token.strip()},
                    extra={},
                ))
            return *_refresh("tiktok"), ""
        except Exception as e:
            return gr.update(), gr.update(), f"**Error:** {e}"

    tt_connect_btn.click(
        _connect_tiktok,
        [tt_method, tt_client_key, tt_client_secret, tt_manual_token, tt_manual_open_id, tt_manual_name],
        [tt_status, tt_disconnect, tt_msg],
    )

    # ── Facebook ──────────────────────────────────────────────────────────────

    def _connect_facebook(app_id, app_secret):
        from ...integrations import facebook as fb_mod
        try:
            fb_mod.connect(app_id, app_secret)
            return *_refresh("facebook"), ""
        except Exception as e:
            return gr.update(), gr.update(), f"**Error:** {e}"

    def _save_facebook_manual(token, page_id, name):
        if not token or not page_id:
            return gr.update(), gr.update(), "**Page Access Token and Page ID are required.**"
        manager.upsert(ConnectedAccount(
            platform="facebook",
            account_id=page_id.strip(),
            display_name=name.strip() or f"Page {page_id.strip()}",
            token={"access_token": token.strip()},
            extra={},
        ))
        return *_refresh("facebook"), "**Saved.**"

    fb_connect_btn.click(_connect_facebook, [fb_app_id, fb_app_secret], [fb_status, fb_disconnect, fb_msg])
    fb_manual_save_btn.click(_save_facebook_manual, [fb_manual_token, fb_manual_page_id, fb_manual_name], [fb_status, fb_disconnect, fb_msg])

    # ── Instagram ─────────────────────────────────────────────────────────────

    def _connect_instagram(app_id, app_secret):
        from ...integrations import instagram as ig_mod
        try:
            ig_mod.connect(app_id, app_secret)
            return *_refresh("instagram"), ""
        except Exception as e:
            return gr.update(), gr.update(), f"**Error:** {e}"

    def _save_instagram_manual(token, account_id, page_id, name):
        if not token or not account_id:
            return gr.update(), gr.update(), "**Access Token and Instagram Account ID are required.**"
        manager.upsert(ConnectedAccount(
            platform="instagram",
            account_id=account_id.strip(),
            display_name=name.strip() or f"@{account_id.strip()}",
            token={"access_token": token.strip()},
            extra={"page_id": page_id.strip()},
        ))
        return *_refresh("instagram"), "**Saved.**"

    ig_connect_btn.click(_connect_instagram, [ig_app_id, ig_app_secret], [ig_status, ig_disconnect, ig_msg])
    ig_manual_save_btn.click(_save_instagram_manual, [ig_manual_token, ig_manual_account_id, ig_manual_page_id, ig_manual_name], [ig_status, ig_disconnect, ig_msg])

    # ── Disconnect ────────────────────────────────────────────────────────────

    yt_disconnect_btn.click(lambda c: _disconnect("youtube", c), [yt_disconnect], [yt_status, yt_disconnect])
    tt_disconnect_btn.click(lambda c: _disconnect("tiktok", c), [tt_disconnect], [tt_status, tt_disconnect])
    fb_disconnect_btn.click(lambda c: _disconnect("facebook", c), [fb_disconnect], [fb_status, fb_disconnect])
    ig_disconnect_btn.click(lambda c: _disconnect("instagram", c), [ig_disconnect], [ig_status, ig_disconnect])
