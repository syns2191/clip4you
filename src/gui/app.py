"""Main Gradio app — assembles all tabs."""

import gradio as gr


_CSS = ".hidden-xy-input { display: none !important; }"


def create_app() -> gr.Blocks:
    with gr.Blocks(title="StoryHero", css=_CSS) as app:
        gr.Markdown("# StoryHero - Short Video Generator")

        with gr.Tabs() as tabs:
            with gr.Tab("Story", id="story"):
                from .tabs.story_tab import create_story_tab
                create_story_tab()

            with gr.Tab("Script Generator", id="scriptgen"):
                from .tabs.scriptgen_tab import create_scriptgen_tab
                scriptgen_refs = create_scriptgen_tab()

            with gr.Tab("Clip Extractor", id="clip"):
                from .tabs.clip_tab import create_clip_tab
                create_clip_tab()

            with gr.Tab("Enhance", id="enhance"):
                from .tabs.enhance_tab import create_enhance_tab
                create_enhance_tab()

            with gr.Tab("Characters", id="characters"):
                from .tabs.characters_tab import create_characters_tab
                create_characters_tab()

            with gr.Tab("Upload", id="upload"):
                from .tabs.upload_tab import create_upload_tab
                create_upload_tab()

            with gr.Tab("Integrations", id="integrations"):
                from .tabs.integrations_tab import create_integrations_tab
                create_integrations_tab()

            with gr.Tab("Settings", id="settings"):
                from .tabs.settings_tab import create_settings_tab
                create_settings_tab()

    return app


def launch_app(share: bool = False, port: int = 7861):
    app = create_app()
    app.queue()
    app.launch(share=share, server_port=port, theme=gr.themes.Soft())
