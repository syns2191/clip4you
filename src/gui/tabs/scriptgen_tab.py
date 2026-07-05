"""Script generation tab."""

import os
import re
import time
import threading
from datetime import datetime
import gradio as gr

from ..components.option_data import (
    SCRIPTGEN_CATEGORY_CHOICES, ART_STYLE_CHOICES,
    CHARACTER_CHOICES, BACKGROUND_CHOICES,
)
from ..pipeline.progress import ProgressCapture

DEFAULT_SCRIPT_DIR = "scripts"


def _save_script(script: str, folder: str, topic: str, overwrite: bool = False) -> str:
    folder = folder.strip() or DEFAULT_SCRIPT_DIR
    os.makedirs(folder, exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", topic.strip()[:40])
    slug = re.sub(r"\s+", "_", slug).lower() or "script"
    base_path = os.path.join(folder, f"{slug}.txt")
    if overwrite or not os.path.exists(base_path):
        path = base_path
    else:
        counter = 2
        while os.path.exists(os.path.join(folder, f"{slug}_{counter}.txt")):
            counter += 1
        path = os.path.join(folder, f"{slug}_{counter}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    return path


def create_scriptgen_tab(story_script_box=None):
    """Create the scriptgen tab. Optionally accepts the Story tab's script textbox for 'Send to Story'."""

    with gr.Row():
        with gr.Column(scale=2):
            topic = gr.Textbox(label="Topic", lines=3, placeholder="What's the story about?")

            with gr.Row():
                category = gr.Dropdown(label="Category", choices=SCRIPTGEN_CATEGORY_CHOICES, value="life-lesson")
                art_style = gr.Dropdown(label="Art Style", choices=ART_STYLE_CHOICES, value="sketch")

            with gr.Row():
                duration = gr.Slider(label="Duration (seconds)", minimum=30, maximum=180, step=10, value=60)
                tone = gr.Textbox(label="Tone", value="reflective and powerful")

            with gr.Row():
                character = gr.Dropdown(label="Character", choices=CHARACTER_CHOICES, value="")
                background = gr.Dropdown(label="Background", choices=BACKGROUND_CHOICES, value="")

            extra = gr.Textbox(label="Extra Instructions", lines=2)

            with gr.Row():
                save_folder = gr.Textbox(label="Save Folder", value=DEFAULT_SCRIPT_DIR, placeholder="scripts/")
                auto_save = gr.Checkbox(label="Auto-save after generate", value=True)
                overwrite = gr.Checkbox(label="Overwrite if exists", value=False)

            with gr.Row():
                gen_btn = gr.Button("Generate Script", variant="primary")
                save_btn = gr.Button("Save Script", interactive=False)
                send_btn = gr.Button("Send to Story Tab", interactive=False)

        with gr.Column(scale=3):
            log_box = gr.Textbox(label="Progress", lines=4, interactive=False)
            script_output = gr.Textbox(label="Generated Script", lines=20, interactive=True)
            save_status = gr.Textbox(label="Save Status", lines=1, interactive=False)

    def generate(topic_val, cat, style, dur, tone_val, char, bg, extra_val, folder_val, do_autosave, do_overwrite):
        if not topic_val.strip():
            yield "Please enter a topic.", "", "", gr.update()
            return

        from ...scriptgen import generate_script
        capture = ProgressCapture()
        result = [None]
        error = [None]

        def _run():
            with capture.capture():
                try:
                    result[0] = generate_script(
                        topic=topic_val, category=cat or "life-lesson",
                        art_style=style or "sketch", duration=int(dur),
                        tone=tone_val or "reflective and powerful",
                        character=char or "", background=bg or "",
                        extra_instructions=extra_val or "",
                    )
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()

        while thread.is_alive():
            time.sleep(0.4)
            yield capture.get_log(), "", "", gr.update()
        thread.join()

        log = capture.get_log()
        if error[0]:
            yield log + f"\n\nERROR: {error[0]}", "", "", gr.update(interactive=False)
            return

        script = result[0] or ""
        save_msg = ""
        if do_autosave and script:
            try:
                path = _save_script(script, folder_val, topic_val, overwrite=do_overwrite)
                save_msg = f"Auto-saved: {path}"
            except Exception as e:
                save_msg = f"Auto-save failed: {e}"

        yield log + "\nDone!", script, save_msg, gr.update(interactive=bool(script))

    gen_btn.click(
        generate,
        inputs=[topic, category, art_style, duration, tone, character, background, extra, save_folder, auto_save, overwrite],
        outputs=[log_box, script_output, save_status, save_btn],
    )

    def manual_save(script, folder_val, topic_val, do_overwrite):
        if not script.strip():
            return "Nothing to save."
        try:
            path = _save_script(script, folder_val, topic_val, overwrite=do_overwrite)
            return f"Saved: {path}"
        except Exception as e:
            return f"Save failed: {e}"

    save_btn.click(
        manual_save,
        inputs=[script_output, save_folder, topic, overwrite],
        outputs=[save_status],
    )

    # Enable send button when script is generated
    script_output.change(
        lambda s: gr.update(interactive=bool(s.strip())),
        inputs=[script_output],
        outputs=[send_btn],
    )

    return {
        "script_output": script_output,
        "send_btn": send_btn,
    }
