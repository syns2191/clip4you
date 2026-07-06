"""Story creation tab with phased pipeline and image wizard."""

import time
import threading
import gradio as gr

from ..components.option_data import (
    VOICE_CHOICES, ELEVENLABS_VOICE_CHOICES, VOICE_PROVIDER_CHOICES,
    ART_STYLE_CHOICES, IMAGE_CATEGORY_CHOICES,
    ANIMATION_CHOICES, FILM_GRAIN_CHOICES, VISUAL_SOURCE_CHOICES,
    CAPTION_STYLE_CHOICES, CAPTION_FONT_CHOICES_GUI,
    CAPTION_ANIMATION_CHOICES, ORIENTATION_CHOICES,
)
from ..pipeline.story_runner import (
    StorySession, execute_phase1, execute_phase2, execute_phase2_gallery,
    regenerate_scene, pick_variant, execute_phase4,
)
from ...imagegen import CACHE_IMG_DIR
from ..pipeline.progress import ProgressCapture
from ..components.image_wizard import (
    get_wizard_state, on_pick_variant, on_regenerate, on_next, on_prev,
)
from ..components.head_tagger import (
    auto_detect_head, set_manual_head, clear_head, on_click_set_head,
)
from ...music import get_music_options, resolve_music_choice, MusicOptions
from ...character import get_library as get_char_library


def create_story_tab():
    session_state = gr.State(None)
    wizard_idx = gr.State(0)

    with gr.Row():
        # === LEFT: Inputs ===
        with gr.Column(scale=2):
            script_text = gr.Textbox(label="Script", lines=8, placeholder="Paste your script or use timeline format...")
            script_file = gr.File(label="Or upload .txt", file_types=[".txt"])

            with gr.Row():
                voice_provider = gr.Radio(
                    label="Voice Engine",
                    choices=VOICE_PROVIDER_CHOICES,
                    value="edge-tts (free)",
                )
            with gr.Row():
                voice = gr.Dropdown(label="Voice Actor", choices=VOICE_CHOICES, value="warm", visible=True)
                el_voice = gr.Dropdown(label="ElevenLabs Voice", choices=ELEVENLABS_VOICE_CHOICES, value=ELEVENLABS_VOICE_CHOICES[0], visible=False)
                voice_rate = gr.Slider(label="Voice Rate %", minimum=-40, maximum=10, step=1, value=-25)

            orientation = gr.Radio(
                label="Video Orientation",
                choices=ORIENTATION_CHOICES,
                value="portrait",
            )

            with gr.Row():
                visuals = gr.Dropdown(label="Visual Source", choices=VISUAL_SOURCE_CHOICES, value="sd")
                art_style = gr.Dropdown(label="Art Style", choices=ART_STYLE_CHOICES, value="")
            with gr.Row():
                character_name = gr.Dropdown(
                    label="Character (optional — for face/visual consistency)",
                    choices=["(none)"] + get_char_library().names(),
                    value="(none)",
                )
                char_refresh_btn = gr.Button("↻", size="sm", min_width=40, scale=0)
            gallery_folder_input = gr.Textbox(
                label="Gallery Folder Path",
                value=CACHE_IMG_DIR,
                placeholder="/path/to/your/images — pick one image per scene in the wizard",
                visible=False,
            )

            with gr.Row():
                image_category = gr.Dropdown(label="Image Category", choices=IMAGE_CATEGORY_CHOICES, value="")
                animation = gr.Dropdown(label="Animation", choices=ANIMATION_CHOICES, value="ken-burns")

            with gr.Row():
                film_grain = gr.Dropdown(label="Film Grain", choices=FILM_GRAIN_CHOICES, value="")
                caption_style = gr.Dropdown(label="Caption Style", choices=CAPTION_STYLE_CHOICES, value="default")

            with gr.Row():
                caption_font = gr.Dropdown(label="Caption Font", choices=CAPTION_FONT_CHOICES_GUI, value="")
                caption_animation = gr.Dropdown(label="Caption Animation", choices=CAPTION_ANIMATION_CHOICES, value="karaoke")

            with gr.Row():
                hook_text = gr.Textbox(label="Hook Text", placeholder="'auto' or custom text", value="auto")
            footnote = gr.Textbox(label="Footnote (outro)", lines=2, placeholder="Title\\nSubtitle")
            output_filename = gr.Textbox(label="Output Filename", placeholder="Leave blank for auto (slug + timestamp)", value="")

            ending_gap = gr.Slider(label="Ending Gap (s)", minimum=0.0, maximum=8.0, step=0.5, value=2.0,
                                   info="Silent pause added after the last scene so the final words aren't cut off")

            with gr.Row():
                music_file = gr.File(label="Music", file_types=[".mp3", ".wav", ".m4a"])
                music_volume = gr.Slider(label="Music Vol", minimum=0.0, maximum=1.0, step=0.05, value=0.3)
            auto_music = gr.Checkbox(label="Auto background music", value=True)

            with gr.Row():
                use_tts_cache = gr.Checkbox(label="Use voice cache", value=True)
                gr.Markdown("<small>Uncheck to regenerate all voices from scratch</small>")

            start_btn = gr.Button("Start Story Pipeline", variant="primary", size="lg")
            cancel_btn = gr.Button("Cancel", variant="stop", size="lg", visible=False)

        # === RIGHT: Output ===
        with gr.Column(scale=3):
            log_box = gr.Textbox(label="Progress", lines=12, interactive=False)

            gr.HTML("""<style>
#gallery-modal-wrap {
    display: none;
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.75);
    z-index: 9000;
    align-items: center;
    justify-content: center;
}
#gallery-modal-wrap.gm-open { display: flex !important; }
#gallery-modal-box {
    background: var(--background-fill-primary, #1f2937);
    border-radius: 12px;
    padding: 16px 20px 20px;
    width: min(92vw, 960px);
    max-height: 88vh;
    overflow-y: auto;
    position: relative;
    box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}
#gallery-modal-box .gallery-modal-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 12px;
}
#gallery-modal-box .gm-title {
    font-size: 1rem; font-weight: 600;
    color: var(--body-text-color, #e5e7eb);
}
#gm-close-x {
    background: none; border: none; cursor: pointer;
    font-size: 20px; line-height: 1; padding: 2px 6px;
    color: var(--body-text-color, #9ca3af); border-radius: 4px;
}
#gm-close-x:hover { background: rgba(255,255,255,0.1); color: white; }
/* Smaller thumbnails inside modal */
#gm-gallery-col .thumbnail-item,
#gm-gallery-col .svelte-1b5n83l {
    max-width: 140px !important;
    max-height: 140px !important;
}
#gm-gallery-col img {
    max-height: 130px !important;
    object-fit: cover !important;
}
</style>
<div id="gallery-modal-wrap">
  <div id="gallery-modal-box">
    <div class="gallery-modal-header">
      <span class="gm-title">Pick an image for this scene</span>
      <button id="gm-close-x" onclick="document.getElementById('gallery-modal-wrap').classList.remove('gm-open')">✕</button>
    </div>
    <div id="gm-gallery-slot"></div>
  </div>
</div>
<script>
(function(){
  function wire(){
    // Move the Gradio gallery column into the modal slot
    var slot = document.getElementById('gm-gallery-slot');
    var col  = document.getElementById('gm-gallery-col');
    if(slot && col && !slot.contains(col)) slot.appendChild(col);

    // Browse button opens modal
    var browseBtn = document.querySelector('#gm-browse-btn button');
    if(browseBtn && !browseBtn._gmWired){
      browseBtn._gmWired = true;
      browseBtn.addEventListener('click', function(e){
        e.stopPropagation();
        var slot2 = document.getElementById('gm-gallery-slot');
        var col2  = document.getElementById('gm-gallery-col');
        if(slot2 && col2 && !slot2.contains(col2)) slot2.appendChild(col2);
        document.getElementById('gallery-modal-wrap').classList.add('gm-open');
      });
    }

    // Close button inside Gradio column closes modal
    var closeBtn = document.querySelector('#gm-close-btn button');
    if(closeBtn && !closeBtn._gmWired){
      closeBtn._gmWired = true;
      closeBtn.addEventListener('click', function(){
        document.getElementById('gallery-modal-wrap').classList.remove('gm-open');
      });
    }

    // Clicking a gallery image also closes modal
    var galDiv = document.getElementById('gm-gallery-col');
    if(galDiv && !galDiv._gmWired){
      galDiv._gmWired = true;
      galDiv.addEventListener('click', function(e){
        if(e.target.closest('.thumbnail-item, button[aria-selected]') ||
           e.target.tagName === 'IMG'){
          setTimeout(function(){
            document.getElementById('gallery-modal-wrap').classList.remove('gm-open');
          }, 200);
        }
      });
    }
  }
  var obs = new MutationObserver(wire);
  obs.observe(document.body, {childList:true, subtree:true});
  wire();
})();
</script>""")

            # --- Image Wizard ---
            with gr.Column(visible=False) as wizard_box:
                gr.Markdown("## Scene Review")
                scene_progress = gr.Markdown("...")
                scene_info = gr.Markdown("...")
                with gr.Row():
                    browse_btn = gr.Button("Browse Images", size="sm", variant="secondary", elem_id="gm-browse-btn")
                    regen_btn = gr.Button("Regenerate", size="sm")
                    wizard_status = gr.Textbox(label="Status", interactive=False, lines=1)

                # Gallery lives here; JS moves it into the modal overlay
                with gr.Column(elem_id="gm-gallery-col"):
                    gallery = gr.Gallery(
                        label="Click an image to pick it for this scene",
                        columns=6,
                        height=400,
                        object_fit="cover",
                        elem_classes=["gm-gallery"],
                    )
                    modal_close_btn = gr.Button("Close", size="sm", elem_id="gm-close-btn")

                gr.Markdown("### Head Position — click image to tag")
                head_preview = gr.HTML(value="")
                # Hidden input for JS click → Python callback ("x,y,timestamp")
                head_click_xy = gr.Textbox(elem_id="head_click_xy", value="", visible=True,
                                           label="", container=False,
                                           elem_classes=["hidden-xy-input"])
                with gr.Row():
                    head_x = gr.Number(label="X", value=0, precision=0, minimum=0, maximum=1080)
                    head_y = gr.Number(label="Y", value=0, precision=0, minimum=0, maximum=1920)
                with gr.Row():
                    head_auto_btn = gr.Button("Auto Detect", size="sm")
                    head_set_btn = gr.Button("Set Manual", size="sm", variant="primary")
                    head_clear_btn = gr.Button("Clear", size="sm")
                head_status = gr.Textbox(label="Head Status", interactive=False, lines=1)

                with gr.Row():
                    prev_btn = gr.Button("< Previous", size="sm")
                    next_btn = gr.Button("Approve & Next >", size="sm", variant="primary")
                    finish_btn = gr.Button("Finish & Render", size="sm", variant="stop")

            # --- Music Picker ---
            with gr.Column(visible=False) as music_picker_box:
                gr.Markdown("## Background Music")
                music_picker_status = gr.Markdown("Searching for music...")
                music_picker_radio = gr.Radio(label="Choose a track", choices=[], value=None)
                with gr.Row():
                    music_confirm_btn = gr.Button("Use Selected Track", variant="primary", size="sm")
                    music_skip_btn = gr.Button("Skip Music", size="sm")

            # --- Final Output ---
            with gr.Column(visible=False) as output_box:
                gr.Markdown("## Result")
                output_video = gr.Video(label="Final Video")
                output_file = gr.File(label="Download")

    music_options_state = gr.State(None)  # holds MusicOptions object

    # === Voice provider toggle ===
    def _on_provider_change(provider):
        use_el = provider == "elevenlabs"
        return gr.update(visible=not use_el), gr.update(visible=use_el)

    voice_provider.change(
        _on_provider_change,
        inputs=[voice_provider],
        outputs=[voice, el_voice],
    )

    # === Gallery folder show/hide ===
    visuals.change(
        lambda v: gr.update(visible=(v == "gallery")),
        inputs=[visuals],
        outputs=[gallery_folder_input],
    )

    # 7 wizard outputs: progress, info, gallery, hx, hy, status, preview_html
    wizard_outputs = [scene_progress, scene_info, gallery, head_x, head_y, head_status, head_preview]

    # All outputs for combined phase1+2 + wizard refresh
    all_phase_outputs = [log_box, wizard_box, output_box, session_state, wizard_idx, start_btn, cancel_btn] + wizard_outputs

    # === File upload handler ===
    def load_script_file(file):
        if file is None:
            return gr.update()
        with open(file.name, "r") as f:
            return f.read()

    script_file.change(load_script_file, inputs=[script_file], outputs=[script_text])

    # === Phase 1 + 2 runner (generator for streaming logs) ===
    _active_session: list = [None]  # mutable reference for cancel

    def run_phases_1_2(
        script, provider_val, voice_val, el_voice_val, rate_val,
        orientation_val, visuals_val, art_val, cat_val,
        anim_val, grain_val, cap_style, cap_font, cap_anim,
        hook_val, footnote_val, out_filename, ending_gap_val, music_f, music_vol, auto_mus,
        tts_cache_val, gallery_folder_val, char_name_val,
    ):
        # Empty wizard outputs placeholder (7 values)
        empty_wiz = ("...", "...", [], 0, 0, "", "")
        btn_running = (gr.update(interactive=False), gr.update(visible=True))
        btn_idle    = (gr.update(interactive=True),  gr.update(visible=False))

        if not script.strip():
            yield ("Please enter a script.", gr.update(), gr.update(), None, 0) + btn_idle + empty_wiz
            return

        if visuals_val == "gallery" and not (gallery_folder_val or "").strip():
            gallery_folder_val = CACHE_IMG_DIR

        output_dir = "output"
        music_path = music_f.name if music_f else None
        rate_str = f"{int(rate_val)}%" if rate_val != 0 else None

        if provider_val == "elevenlabs":
            effective_voice = el_voice_val or ELEVENLABS_VOICE_CHOICES[0]
        else:
            effective_voice = voice_val or "warm"

        resolved_char = char_name_val if char_name_val and char_name_val != "(none)" else ""
        session = StorySession(
            script=script, output_dir=output_dir,
            voice=effective_voice, voice_rate=rate_str,
            music_path=music_path, music_volume=music_vol,
            auto_music=auto_mus, visuals=visuals_val or "sd",
            art_style=art_val or "", image_category=cat_val or "",
            animation=anim_val or "ken-burns", film_grain=grain_val or "",
            caption_style=cap_style or "default", caption_font=cap_font or "",
            caption_animation=cap_anim or "karaoke",
            hook_text=hook_val or "", footnote=footnote_val.replace("\\n", "\n") if footnote_val else "",
            output_filename=out_filename or "",
            use_tts_cache=bool(tts_cache_val),
            orientation=orientation_val or "portrait",
            ending_gap=float(ending_gap_val or 2.0),
            gallery_folder=gallery_folder_val or "",
            character_name=resolved_char,
        )
        _active_session[0] = session

        capture = ProgressCapture()
        error = [None]

        def _run():
            with capture.capture():
                try:
                    execute_phase1(session)
                    if session.visuals == "gallery":
                        execute_phase2_gallery(session)
                    else:
                        execute_phase2(session)
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()

        # Show cancel button, disable start while running
        yield (capture.get_log(), gr.update(), gr.update(), session, 0) + btn_running + empty_wiz

        while thread.is_alive():
            time.sleep(0.4)
            yield (capture.get_log(), gr.update(), gr.update(), session, 0) + btn_running + empty_wiz
        thread.join()
        _active_session[0] = None

        log = capture.get_log()
        if session.cancelled:
            yield (log + "\n\nCancelled.", gr.update(visible=False), gr.update(visible=False), None, 0) + btn_idle + empty_wiz
            return
        if error[0]:
            yield (log + f"\n\nERROR: {error[0]}", gr.update(visible=False), gr.update(visible=False), session, 0) + btn_idle + empty_wiz
            return

        # Success — show wizard and populate it with first scene
        wiz_vals = get_wizard_state(session, 0)
        yield (log + "\n\n-> Ready for review. Check scenes below.", gr.update(visible=True), gr.update(visible=False), session, 0) + btn_idle + wiz_vals

    def refresh_characters():
        names = get_char_library().names()
        return gr.update(choices=["(none)"] + names)

    char_refresh_btn.click(refresh_characters, inputs=[], outputs=[character_name])

    def cancel_pipeline():
        s = _active_session[0]
        if s is not None:
            s.cancelled = True
        return gr.update(visible=False), gr.update(interactive=True)

    cancel_btn.click(
        cancel_pipeline,
        inputs=[],
        outputs=[cancel_btn, start_btn],
    )

    start_btn.click(
        run_phases_1_2,
        inputs=[
            script_text, voice_provider, voice, el_voice, voice_rate,
            orientation, visuals, art_style, image_category, animation, film_grain,
            caption_style, caption_font, caption_animation,
            hook_text, footnote, output_filename, ending_gap, music_file, music_volume, auto_music,
            use_tts_cache, gallery_folder_input, character_name,
        ],
        outputs=all_phase_outputs,
    )

    # === Gallery click → pick variant ===
    def _on_gallery_pick(session, idx, evt: gr.SelectData):
        if session is None:
            return (session, "No session") + get_wizard_state(session, 0)
        session, status = on_pick_variant(session, idx, evt)
        vals = get_wizard_state(session, idx)
        return (session, status) + vals

    gallery.select(
        _on_gallery_pick,
        inputs=[session_state, wizard_idx],
        outputs=[session_state, wizard_status] + wizard_outputs,
    )

    # === Regenerate ===
    def _on_regen(session, idx):
        if session is None:
            return (session, "No session") + get_wizard_state(session, 0)
        if session.visuals == "gallery":
            return (session, "Regenerate is not available in gallery mode — click an image to pick it.") + get_wizard_state(session, idx)
        capture = ProgressCapture()
        with capture.capture():
            session, images, status = on_regenerate(session, idx)
        vals = get_wizard_state(session, idx)
        return (session, status) + vals

    regen_btn.click(
        _on_regen,
        inputs=[session_state, wizard_idx],
        outputs=[session_state, wizard_status] + wizard_outputs,
    )

    # === Navigation ===
    def _go_next(session, idx):
        new_idx = on_next(session, idx)
        vals = get_wizard_state(session, new_idx)
        return (new_idx,) + vals

    def _go_prev(session, idx):
        new_idx = on_prev(session, idx)
        vals = get_wizard_state(session, new_idx)
        return (new_idx,) + vals

    next_btn.click(_go_next, [session_state, wizard_idx], [wizard_idx] + wizard_outputs)
    prev_btn.click(_go_prev, [session_state, wizard_idx], [wizard_idx] + wizard_outputs)

    # === Click-to-tag: JS writes "x,y,timestamp" to hidden textbox, .change() triggers Python ===
    def _on_click_tag(session, idx, xy_raw):
        print('session:', session, 'idx:', idx, 'xy_raw:', xy_raw)
        if session is None or not xy_raw:
            return 0, 0, "", "", session
        x, y, status, preview, session = on_click_set_head(session, idx, xy_raw)
        return x, y, status, preview, session

    head_click_xy.change(
        _on_click_tag,
        inputs=[session_state, wizard_idx, head_click_xy],
        outputs=[head_x, head_y, head_status, head_preview, session_state],
    )

    # === Head controls (auto detect / set manual / clear) ===
    head_auto_btn.click(
        lambda s, i: auto_detect_head(s, i),
        [session_state, wizard_idx],
        [head_x, head_y, head_status, head_preview],
    )
    head_set_btn.click(
        lambda s, i, x, y: set_manual_head(s, i, x, y),
        [session_state, wizard_idx, head_x, head_y],
        [head_status, head_preview],
    )
    head_clear_btn.click(
        lambda s, i: clear_head(s, i),
        [session_state, wizard_idx],
        [head_x, head_y, head_status, head_preview],
    )

    # === Finish & Render: show music picker if auto_music and no file uploaded ===
    def on_finish_click(session):
        """Fetch music options and show picker, or go straight to render if music already set."""
        if session is None:
            return (
                gr.update(visible=True), gr.update(visible=False),
                gr.update(visible=False), None,
                "...", gr.update(choices=[], value=None),
            )

        if session.music_path or not session.auto_music:
            # No picker needed — signal to render directly with a sentinel
            return (
                gr.update(visible=False), gr.update(visible=True),
                gr.update(visible=False), None,
                "Music already set — click **Use Selected Track** or **Skip Music** to render.",
                gr.update(choices=[("Render now (music already configured)", "render_direct")], value="render_direct"),
            )

        from ...story import VOICE_MUSIC_MAP
        genre = VOICE_MUSIC_MAP.get(session.voice, "cinematic background")
        opts = get_music_options("cinematic", "narrated story", genre=genre)

        choices = []
        if opts.local:
            for name in opts.local:
                label = f"[Local] {name}"
                if name == opts.ai_local:
                    label += "  ← AI pick"
                choices.append((label, f"local:{name}"))
        for i, yt in enumerate(opts.youtube):
            channel = f" · {yt.channel}" if yt.channel else ""
            choices.append((f"[YouTube] {yt.title} ({yt.duration}){channel}", f"yt:{i}"))
        choices.append(("Skip — no music", "skip"))

        default = f"local:{opts.ai_local}" if opts.ai_local else (choices[0][1] if choices else "skip")
        status = f"Found **{len(opts.local)}** local track(s) and **{len(opts.youtube)}** YouTube results."

        return (
            gr.update(visible=False), gr.update(visible=True),
            gr.update(visible=False), opts,
            status, gr.update(choices=choices, value=default),
        )

    finish_btn.click(
        on_finish_click,
        inputs=[session_state],
        outputs=[
            wizard_box, music_picker_box, output_box, music_options_state,
            music_picker_status, music_picker_radio,
        ],
    )

    # === Render after music pick ===
    def _run_phase4_with_music(session, opts, choice):
        if session is None:
            yield (
                "No session", gr.update(visible=False),
                gr.update(visible=False), None, None,
            )
            return

        if choice and choice != "render_direct":
            resolved = resolve_music_choice(choice, opts, session.output_dir) if opts else None
            session.music_path = resolved

        capture = ProgressCapture()
        error = [None]
        result = [None]

        def _run():
            with capture.capture():
                try:
                    result[0] = execute_phase4(session)
                except Exception as e:
                    error[0] = e

        thread = threading.Thread(target=_run)
        thread.start()

        while thread.is_alive():
            time.sleep(0.4)
            yield capture.get_log(), gr.update(), gr.update(visible=False), None, None
        thread.join()

        log = capture.get_log()
        if error[0]:
            yield log + f"\n\nERROR: {error[0]}", gr.update(visible=False), gr.update(visible=False), None, None
            return

        yield log, gr.update(visible=False), gr.update(visible=True), result[0], result[0]

    music_confirm_btn.click(
        _run_phase4_with_music,
        inputs=[session_state, music_options_state, music_picker_radio],
        outputs=[log_box, music_picker_box, output_box, output_video, output_file],
    )
    music_skip_btn.click(
        lambda s, o: _run_phase4_with_music(s, o, "skip"),
        inputs=[session_state, music_options_state],
        outputs=[log_box, music_picker_box, output_box, output_video, output_file],
    )
