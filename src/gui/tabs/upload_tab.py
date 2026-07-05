"""Upload tab — YouTube Shorts upload."""

import time
import threading
import gradio as gr

from ..components.option_data import PRIVACY_CHOICES
from ..pipeline.progress import ProgressCapture


def create_upload_tab():
    with gr.Row():
        with gr.Column(scale=2):
            video_file = gr.File(label="Video to Upload", file_types=[".mp4"])
            title = gr.Textbox(label="Title", placeholder="Leave empty for AI-generated")
            description = gr.Textbox(label="Description", lines=3, placeholder="Leave empty for AI-generated")
            tags = gr.Textbox(label="Tags (comma-separated)", placeholder="Leave empty for AI-generated")
            privacy = gr.Dropdown(label="Privacy", choices=PRIVACY_CHOICES, value="private")
            auto_ai = gr.Checkbox(label="Auto AI metadata", value=True)
            upload_btn = gr.Button("Upload to YouTube", variant="primary", size="lg")

        with gr.Column(scale=3):
            log_box = gr.Textbox(label="Progress", lines=8, interactive=False)
            result_box = gr.Markdown("Upload result will appear here.")

    def do_upload(file, title_val, desc_val, tags_val, priv, ai_meta):
        if not file:
            yield "Upload a video.", "No file selected."
            return

        from ...upload import upload_to_youtube

        capture = ProgressCapture()
        error = [None]
        result = [None]

        def _run():
            with capture.capture():
                try:
                    result[0] = upload_to_youtube(
                        file.name,
                        title=title_val or None,
                        description=desc_val or None,
                        tags=tags_val or None,
                        privacy=priv or "private",
                        auto_metadata=ai_meta,
                    )
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()
        while thread.is_alive():
            time.sleep(0.4)
            yield capture.get_log(), "Uploading..."
        thread.join()

        log = capture.get_log()
        if error[0]:
            yield log + f"\nERROR: {error[0]}", f"Upload failed: {error[0]}"
        elif result[0]:
            yield log + "\nDone!", f"**Uploaded!**\n\n{result[0]}"
        else:
            yield log + "\nDone!", "Upload completed."

    upload_btn.click(
        do_upload,
        inputs=[video_file, title, description, tags, privacy, auto_ai],
        outputs=[log_box, result_box],
    )
