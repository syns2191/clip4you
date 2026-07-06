"""Upload tab — multi-platform upload with per-platform progress."""

import os
import time
import threading
import gradio as gr

from ..components.option_data import PRIVACY_CHOICES
from ..pipeline.progress import ProgressCapture
from ...integrations.manager import get_manager

PLATFORMS = ["YouTube", "TikTok", "Facebook", "Instagram"]


def _choices_for(platform: str) -> list[str]:
    accts = get_manager().for_platform(platform.lower())
    return [f"{a.display_name} ({a.account_id})" for a in accts] or ["(none — connect in Integrations tab)"]


def create_upload_tab():
    manager = get_manager()

    with gr.Row():
        with gr.Column(scale=2):
            video_file = gr.File(label="Video to Upload", file_types=[".mp4"])
            platform = gr.Dropdown(label="Platform", choices=PLATFORMS, value="YouTube")
            account = gr.Dropdown(
                label="Account",
                choices=_choices_for("YouTube"),
                value=None,
                info="Connect accounts in the Integrations tab",
            )
            title = gr.Textbox(label="Title", placeholder="Leave empty for AI-generated")
            description = gr.Textbox(label="Description", lines=3, placeholder="Leave empty for AI-generated")
            tags = gr.Textbox(label="Tags (comma-separated)", placeholder="Leave empty for AI-generated")
            privacy = gr.Dropdown(label="Privacy", choices=PRIVACY_CHOICES, value="private")
            auto_ai = gr.Checkbox(label="Auto AI metadata", value=True)

            with gr.Row():
                upload_btn = gr.Button("Upload", variant="primary", size="lg")
                cancel_btn = gr.Button("Cancel", variant="stop", size="lg", visible=False)

        with gr.Column(scale=3):
            progress_bar = gr.Slider(
                label="Upload progress",
                minimum=0, maximum=100, value=0, step=1,
                interactive=False, visible=False,
            )
            log_box = gr.Textbox(label="Progress log", lines=10, interactive=False)
            result_box = gr.Markdown("Upload result will appear here.")

    platform.change(
        lambda p: gr.update(choices=_choices_for(p), value=None),
        inputs=[platform],
        outputs=[account],
    )

    _cancel_flag: list[bool] = [False]

    def do_upload(file, platform_val, account_val, title_val, desc_val, tags_val, priv, ai_meta):
        _cancel_flag[0] = False

        if not file:
            yield gr.update(visible=False), gr.update(visible=False), "Please select a video file.", "No file selected."
            return
        if not account_val or account_val.startswith("(none"):
            yield gr.update(visible=False), gr.update(visible=False), "", "**No account selected.** Connect one in the Integrations tab."
            return

        account_id = account_val.rsplit("(", 1)[-1].rstrip(")")
        acct = manager.get(platform_val.lower(), account_id)
        if acct is None:
            yield gr.update(visible=False), gr.update(visible=False), "", "**Account not found.** Try reconnecting in the Integrations tab."
            return

        capture = ProgressCapture()
        error = [None]
        result = [None]
        pct: list[int] = [0]

        def _progress(step: str, percent: int):
            pct[0] = percent
            print(step)

        def _run():
            with capture.capture():
                try:
                    if platform_val == "YouTube":
                        _upload_youtube(file.name, acct, title_val, desc_val, tags_val, priv, ai_meta, result, _progress, _cancel_flag)
                    elif platform_val == "TikTok":
                        _upload_tiktok(file.name, acct, title_val, result, _progress, _cancel_flag)
                    elif platform_val == "Facebook":
                        _upload_facebook(file.name, acct, title_val, desc_val, priv, result, _progress, _cancel_flag)
                    elif platform_val == "Instagram":
                        _upload_instagram(file.name, acct, title_val, desc_val, result, _progress, _cancel_flag)
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()

        # Show progress bar + cancel button
        yield gr.update(value=pct[0], visible=True), gr.update(visible=False), capture.get_log(), gr.update()

        while thread.is_alive():
            time.sleep(0.3)
            yield gr.update(value=pct[0], visible=True), gr.update(visible=False), capture.get_log(), gr.update()
        thread.join()

        log = capture.get_log()

        if _cancel_flag[0]:
            yield gr.update(value=0, visible=False), gr.update(visible=False), log + "\n\nCancelled.", "Upload cancelled."
            return
        if error[0]:
            yield gr.update(value=pct[0], visible=False), gr.update(visible=False), log + f"\n\nERROR: {error[0]}", f"**Upload failed:** {error[0]}"
            return

        yield gr.update(value=100, visible=False), gr.update(visible=False), log + "\n\nDone!", f"**Uploaded!**\n\n{result[0]}"

    def cancel_upload():
        _cancel_flag[0] = True
        return gr.update(visible=False), gr.update(interactive=True)

    upload_btn.click(
        do_upload,
        inputs=[video_file, platform, account, title, description, tags, privacy, auto_ai],
        outputs=[progress_bar, cancel_btn, log_box, result_box],
    )
    cancel_btn.click(cancel_upload, [], [cancel_btn, upload_btn])


# ── Platform implementations ──────────────────────────────────────────────────

def _upload_youtube(video_path, acct, title, description, tags, privacy, auto_ai, result, progress, cancel_flag):
    from ...integrations.youtube import get_service
    from googleapiclient.http import MediaFileUpload

    progress("Preparing metadata...", 2)

    if auto_ai and not title:
        from ...upload import _generate_story_metadata
        try:
            progress("Generating AI metadata...", 5)
            meta = _generate_story_metadata(open(video_path).read()[:500])
            title = meta.get("title", "") or title
            description = description or meta.get("description", "")
            tags = tags or ",".join(meta.get("tags", []))
        except Exception:
            pass

    tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    for req in ["Shorts", "YouTubeShorts"]:
        if req not in tags_list:
            tags_list.append(req)

    title = title or "My Short"
    if "#Shorts" not in title:
        title = f"{title} #Shorts"
    if description and "#Shorts" not in description:
        description += "\n\n#Shorts"
    elif not description:
        description = "#Shorts"

    progress("Authenticating with YouTube...", 8)
    youtube = get_service(acct)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags_list[:500],
            "categoryId": "22",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }

    file_size = os.path.getsize(video_path)
    print(f"Uploading '{os.path.basename(video_path)}' ({file_size / 1024 / 1024:.1f} MB) to YouTube as '{acct.display_name}'...")

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        if cancel_flag[0]:
            print("Upload cancelled.")
            return
        status, response = request.next_chunk()
        if status:
            upload_pct = int(status.progress() * 100)
            # Map 10–95 range to upload progress
            display_pct = 10 + int(upload_pct * 0.85)
            progress(f"Uploading... {upload_pct}%", display_pct)

    video_id = response["id"]
    progress("Upload complete!", 100)
    print(f"YouTube URL: https://youtube.com/shorts/{video_id}")
    result[0] = f"https://youtube.com/shorts/{video_id}"


def _upload_tiktok(video_path, acct, title, result, progress, cancel_flag):
    import requests

    token = acct.token.get("access_token", "")
    if not token:
        raise ValueError("TikTok token missing — reconnect in Integrations tab.")

    file_size = os.path.getsize(video_path)
    print(f"Uploading '{os.path.basename(video_path)}' ({file_size / 1024 / 1024:.1f} MB) to TikTok as '{acct.display_name}'...")

    progress("Initialising TikTok upload...", 10)
    if cancel_flag[0]:
        return

    init_resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "post_info": {
                "title": title or "Untitled",
                "privacy_level": "SELF_ONLY",
                "disable_duet": False,
                "disable_stitch": False,
                "disable_comment": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    data = init_resp.json().get("data", {})
    upload_url = data["upload_url"]
    publish_id = data["publish_id"]

    progress("Uploading video chunk...", 30)
    if cancel_flag[0]:
        return

    CHUNK = 5 * 1024 * 1024
    with open(video_path, "rb") as f:
        uploaded = 0
        chunk_num = 0
        while True:
            if cancel_flag[0]:
                return
            chunk = f.read(CHUNK)
            if not chunk:
                break
            start = uploaded
            end = uploaded + len(chunk) - 1
            requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(len(chunk)),
                },
                data=chunk,
                timeout=300,
            ).raise_for_status()
            uploaded += len(chunk)
            pct = 30 + int((uploaded / file_size) * 60)
            progress(f"Uploading... {int(uploaded / file_size * 100)}%", pct)

    progress("Upload queued for processing...", 100)
    print(f"TikTok publish_id={publish_id}")
    result[0] = f"TikTok upload queued. Publish ID: `{publish_id}`"


def _upload_facebook(video_path, acct, title, description, privacy, result, progress, cancel_flag):
    import requests

    token = acct.token.get("access_token", "")
    page_id = acct.account_id
    file_size = os.path.getsize(video_path)
    print(f"Uploading '{os.path.basename(video_path)}' ({file_size / 1024 / 1024:.1f} MB) to Facebook page '{acct.display_name}'...")

    progress("Starting Facebook upload...", 10)
    if cancel_flag[0]:
        return

    # Use requests-toolbelt or manual chunked read for progress tracking
    uploaded = [0]

    class _ProgressFile:
        def __init__(self, path):
            self._f = open(path, "rb")
            self._size = file_size

        def read(self, size=-1):
            data = self._f.read(size)
            uploaded[0] += len(data)
            pct = 10 + int((uploaded[0] / self._size) * 80)
            progress(f"Uploading... {int(uploaded[0] / self._size * 100)}%", pct)
            return data

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self._f.close()

    with _ProgressFile(video_path) as f:
        resp = requests.post(
            f"https://graph.facebook.com/v19.0/{page_id}/videos",
            data={
                "title": title or "",
                "description": description or "",
                "published": "true" if privacy == "public" else "false",
                "access_token": token,
            },
            files={"source": ("video.mp4", f, "video/mp4")},
            timeout=300,
        )
    resp.raise_for_status()
    video_id = resp.json().get("id", "")
    progress("Upload complete!", 100)
    print(f"Facebook video_id={video_id}")
    result[0] = f"Facebook video ID: `{video_id}`"


def _upload_instagram(video_path, acct, title, description, result, progress, cancel_flag):
    import requests

    token = acct.token.get("access_token", "")
    ig_id = acct.account_id
    page_id = acct.extra.get("page_id", "")
    file_size = os.path.getsize(video_path)

    if not page_id:
        raise ValueError("Instagram upload requires a linked Facebook Page. Reconnect in Integrations tab.")

    print(f"Uploading '{os.path.basename(video_path)}' ({file_size / 1024 / 1024:.1f} MB) to Instagram '{acct.display_name}'...")

    # Step 1: upload video to linked FB page (unpublished)
    progress("Step 1/4 — Uploading video to Facebook...", 10)
    if cancel_flag[0]:
        return

    uploaded = [0]

    class _ProgressFile:
        def __init__(self, path):
            self._f = open(path, "rb")

        def read(self, size=-1):
            data = self._f.read(size)
            uploaded[0] += len(data)
            pct = 10 + int((uploaded[0] / file_size) * 40)
            progress(f"Step 1/4 — Uploading... {int(uploaded[0] / file_size * 100)}%", pct)
            return data

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self._f.close()

    with _ProgressFile(video_path) as f:
        fb_resp = requests.post(
            f"https://graph.facebook.com/v19.0/{page_id}/videos",
            data={"published": "false", "access_token": token},
            files={"source": ("video.mp4", f, "video/mp4")},
            timeout=300,
        )
    fb_resp.raise_for_status()
    fb_video_id = fb_resp.json().get("id", "")

    # Step 2: get public URL
    progress("Step 2/4 — Getting video URL...", 55)
    if cancel_flag[0]:
        return
    url_resp = requests.get(
        f"https://graph.facebook.com/v19.0/{fb_video_id}",
        params={"fields": "permalink_url", "access_token": token},
        timeout=15,
    )
    video_url = url_resp.json().get("permalink_url", "") if url_resp.ok else ""
    if not video_url:
        raise RuntimeError(f"Uploaded to Facebook (ID: {fb_video_id}) but could not get public URL for Instagram Reel.")

    # Step 3: create Reel container
    progress("Step 3/4 — Creating Instagram Reel container...", 70)
    if cancel_flag[0]:
        return
    container_resp = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": description or title or "",
            "access_token": token,
        },
        timeout=60,
    )
    container_resp.raise_for_status()
    container_id = container_resp.json().get("id", "")

    # Step 4: publish
    progress("Step 4/4 — Publishing Reel...", 90)
    if cancel_flag[0]:
        return
    pub_resp = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    pub_resp.raise_for_status()
    media_id = pub_resp.json().get("id", "")
    progress("Published!", 100)
    print(f"Instagram Reel media_id={media_id}")
    result[0] = f"Instagram Reel published. Media ID: `{media_id}`"
