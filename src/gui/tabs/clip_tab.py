"""Clip extraction tab."""

import time
import threading
import gradio as gr

from ..components.option_data import (
    CLIP_CATEGORY_CHOICES, REFRAME_CHOICES, SFX_CHOICES,
    VOICE_CHOICES,
)
from ..pipeline.clip_runner import ClipSession, step1_transcribe, step2_render
from ..pipeline.progress import ProgressCapture


def create_clip_tab():
    clip_session = gr.State(None)

    with gr.Row():
        with gr.Column(scale=2):
            video_file = gr.File(label="Upload Video", file_types=[".mp4", ".mkv", ".mov", ".avi"])
            youtube_url = gr.Textbox(label="Or YouTube URL", placeholder="https://youtube.com/watch?v=...")

            with gr.Row():
                num_clips = gr.Slider(label="Clips", minimum=1, maximum=10, step=1, value=5)
                reframe = gr.Dropdown(label="Reframe", choices=REFRAME_CHOICES, value="crop")

            with gr.Row():
                start_time = gr.Number(label="Start (sec)", value=0, precision=1)
                end_time = gr.Number(label="End (sec)", value=0, precision=1)

            category = gr.Dropdown(label="Category", choices=CLIP_CATEGORY_CHOICES, value="auto")
            prompt = gr.Textbox(label="Guidance/Prompt", lines=2)

            with gr.Accordion("Audio & Effects", open=False):
                with gr.Row():
                    music_ai = gr.Checkbox(label="AI Music")
                    music_genre = gr.Textbox(label="Genre", scale=2)
                    music_vol = gr.Slider(label="Music Vol", minimum=0.0, maximum=1.0, value=1.0, step=0.05)
                sfx = gr.Dropdown(label="SFX", choices=SFX_CHOICES, value="")
                with gr.Row():
                    emoji_toggle = gr.Checkbox(label="Emoji")
                    montage = gr.Checkbox(label="Montage")
                    enhance = gr.Checkbox(label="Enhance")

            extract_btn = gr.Button("Extract Clips", variant="primary", size="lg")

        with gr.Column(scale=3):
            log_box = gr.Textbox(label="Progress", lines=10, interactive=False)

            with gr.Column(visible=False) as select_box:
                gr.Markdown("### Select Clips to Render")
                clip_table = gr.Dataframe(
                    headers=["#", "Title", "Time", "Score", "Category", "Reason"],
                    interactive=False,
                )
                clip_checks = gr.CheckboxGroup(label="Select clips", choices=[])
                render_btn = gr.Button("Render Selected", variant="primary")

            with gr.Column(visible=False) as result_box:
                gr.Markdown("### Rendered Clips")
                result_files = gr.File(label="Download", file_count="multiple")

    def do_extract(
        file, url, n_clips, reframe_val, start_val, end_val,
        cat, prompt_val, mus_ai, mus_genre, mus_vol_val,
        sfx_val, emoji_val, montage_val, enhance_val,
    ):
        if not file and not url:
            yield "Upload a video or enter a YouTube URL.", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), None
            return

        input_path = file.name if file else None

        if not input_path and url:
            from ...download import download_youtube
            capture = ProgressCapture()
            dl_result = [None]
            def _dl():
                with capture.capture():
                    dl_result[0] = download_youtube(url, "output/downloaded_source.mp4")
            t = threading.Thread(target=_dl)
            t.start()
            while t.is_alive():
                time.sleep(0.4)
                yield capture.get_log(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), None
            t.join()
            input_path = dl_result[0]
            if not input_path:
                yield capture.get_log() + "\nFailed to download.", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), None
                return

        session = ClipSession(
            input_path=input_path, output_dir="output",
            num_clips=int(n_clips), reframe=reframe_val or "crop",
            start=start_val if start_val > 0 else None,
            end=end_val if end_val > 0 else None,
            video_category=cat or "auto", user_prompt=prompt_val or "",
            music_ai=mus_ai, music_genre=mus_genre or None,
            music_level=mus_vol_val, sfx=sfx_val or None,
            emoji=emoji_val, montage=montage_val, enhance=enhance_val,
        )

        capture = ProgressCapture()
        error = [None]

        def _run():
            with capture.capture():
                try:
                    step1_transcribe(session)
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()
        while thread.is_alive():
            time.sleep(0.4)
            yield capture.get_log(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), None
        thread.join()

        log = capture.get_log()
        if error[0] or not session.candidates:
            yield log + f"\n{'ERROR: ' + str(error[0]) if error[0] else 'No clips found.'}", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), None
            return

        rows = []
        choices = []
        for i, c in enumerate(session.candidates):
            rows.append([i+1, c.title, f"{c.start:.1f}-{c.end:.1f}s", c.score, c.category, c.reason[:60]])
            choices.append(str(i+1))

        yield (
            log, gr.update(visible=True), gr.update(value=rows),
            gr.update(choices=choices, value=choices),
            gr.update(), gr.update(), session,
        )

    extract_btn.click(
        do_extract,
        inputs=[
            video_file, youtube_url, num_clips, reframe, start_time, end_time,
            category, prompt, music_ai, music_genre, music_vol,
            sfx, emoji_toggle, montage, enhance,
        ],
        outputs=[log_box, select_box, clip_table, clip_checks, result_box, result_files, clip_session],
    )

    def do_render(session, selected):
        if session is None:
            yield "No clips to render.", gr.update(), gr.update()
            return

        indices = [int(s) - 1 for s in selected] if selected else list(range(len(session.candidates)))

        capture = ProgressCapture()
        error = [None]

        def _run():
            with capture.capture():
                try:
                    step2_render(session, indices)
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()
        while thread.is_alive():
            time.sleep(0.4)
            yield capture.get_log(), gr.update(), gr.update()
        thread.join()

        log = capture.get_log()
        if error[0]:
            yield log + f"\nERROR: {error[0]}", gr.update(visible=False), gr.update()
        else:
            yield log + "\nDone!", gr.update(visible=True), session.rendered_paths

    render_btn.click(
        do_render,
        inputs=[clip_session, clip_checks],
        outputs=[log_box, result_box, result_files],
    )
