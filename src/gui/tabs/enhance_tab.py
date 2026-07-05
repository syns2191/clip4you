"""Enhance tab — AI post-render enhancement."""

import time
import threading
import gradio as gr

from ..pipeline.progress import ProgressCapture


def create_enhance_tab():
    with gr.Row():
        with gr.Column(scale=2):
            video_file = gr.File(label="Input Video", file_types=[".mp4", ".mkv", ".mov"])
            title = gr.Textbox(label="Title (context)", placeholder="Helps AI understand the clip")
            prompt = gr.Textbox(label="Enhancement Prompt", lines=3, placeholder="e.g. 'zoom on reactions, add dramatic SFX'")
            enhance_btn = gr.Button("Enhance Video", variant="primary", size="lg")

        with gr.Column(scale=3):
            log_box = gr.Textbox(label="Progress", lines=8, interactive=False)
            output_video = gr.Video(label="Enhanced Video")
            output_file = gr.File(label="Download")

    def do_enhance(file, title_val, prompt_val):
        if not file:
            yield "Upload a video.", None, None
            return

        from ...enhance import enhance_clip
        import os

        input_path = file.name
        output_path = input_path + "_enhanced.mp4"

        capture = ProgressCapture()
        error = [None]

        def _run():
            with capture.capture():
                try:
                    enhance_clip(input_path, output_path, title=title_val or "", user_prompt=prompt_val or "")
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()
        while thread.is_alive():
            time.sleep(0.4)
            yield capture.get_log(), None, None
        thread.join()

        log = capture.get_log()
        if error[0]:
            yield log + f"\nERROR: {error[0]}", None, None
        elif os.path.exists(output_path):
            yield log + "\nDone!", output_path, output_path
        else:
            yield log + "\nFailed to produce output.", None, None

    enhance_btn.click(
        do_enhance,
        inputs=[video_file, title, prompt],
        outputs=[log_box, output_video, output_file],
    )
