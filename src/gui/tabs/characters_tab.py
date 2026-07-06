"""Characters tab — create and manage named characters for consistent image generation."""

import gradio as gr

from ...character import get_library, generate_character_portrait, Character
from ...imagegen import ART_STYLES

_STYLE_CHOICES = [(v["name"], k) for k, v in ART_STYLES.items()]
_PROVIDER_CHOICES = ["openai", "sd"]


def _char_choices() -> list[str]:
    return get_library().names()


def _char_info(name: str):
    if not name:
        return "", "cinematic", None, gr.update(visible=False)
    char = get_library().get(name)
    if not char:
        return "", "cinematic", None, gr.update(visible=False)
    img = char.portrait_path if char.portrait_path else None
    return char.description, char.art_style, img, gr.update(visible=img is not None)


def create_characters_tab():
    with gr.Row():
        # Left panel — create / edit
        with gr.Column(scale=2):
            gr.Markdown("### Create / Edit Character")
            char_name = gr.Textbox(label="Character Name", placeholder="e.g. Maya, The Warrior, Narrator")
            char_desc = gr.Textbox(
                label="Description",
                lines=4,
                placeholder="Describe the character's appearance: age, gender, skin tone, hair, clothing, expression style..."
            )
            char_style = gr.Dropdown(
                label="Art Style",
                choices=_STYLE_CHOICES,
                value="cinematic",
            )
            char_provider = gr.Radio(
                label="Image Provider",
                choices=_PROVIDER_CHOICES,
                value="openai",
            )
            char_ref = gr.Image(
                label="Reference Image (optional — upload a face photo for extra consistency)",
                type="filepath",
                height=200,
            )

            with gr.Row():
                generate_btn = gr.Button("Generate Portrait", variant="primary", size="lg")
                save_btn = gr.Button("Save without generating", variant="secondary", size="sm")

            gen_status = gr.Markdown("")

        # Right panel — library
        with gr.Column(scale=3):
            gr.Markdown("### Character Library")
            char_select = gr.Dropdown(
                label="Select character",
                choices=_char_choices(),
                value=None,
            )
            portrait_preview = gr.Image(label="Portrait", height=320, visible=False)
            char_desc_view = gr.Textbox(label="Description", interactive=False, lines=3)

            with gr.Row():
                load_btn = gr.Button("Load into editor", size="sm")
                delete_btn = gr.Button("Delete", variant="stop", size="sm")
            delete_msg = gr.Markdown("")

    # ── Handlers ──────────────────────────────────────────────────────────────

    def do_generate(name, desc, style, provider, ref_path):
        if not name.strip():
            yield gr.update(visible=False), "**Name is required.**", gr.update()
            return
        if not desc.strip():
            yield gr.update(visible=False), "**Description is required.**", gr.update()
            return

        yield gr.update(visible=False), "Generating portrait...", gr.update()

        path = generate_character_portrait(
            name=name.strip(),
            description=desc.strip(),
            art_style=style,
            provider=provider,
            reference_image_path=ref_path or "",
        )

        if path:
            yield (
                gr.update(value=path, visible=True),
                f"**Saved!** Portrait for **{name}** is ready.",
                gr.update(choices=_char_choices(), value=name.strip()),
            )
        else:
            yield gr.update(visible=False), "**Generation failed.** Check your provider settings.", gr.update()

    def do_save(name, desc, style):
        if not name.strip():
            return "**Name is required.**", gr.update()
        lib = get_library()
        char = lib.get(name.strip()) or Character(name=name.strip(), description=desc.strip(), art_style=style)
        char.description = desc.strip()
        char.art_style = style
        lib.upsert(char)
        return f"**Saved** character *{name.strip()}* (no portrait generated).", gr.update(choices=_char_choices(), value=name.strip())

    def do_load(selected_name):
        desc, style, img, img_vis = _char_info(selected_name)
        return desc, style, img, img_vis

    def do_select(selected_name):
        desc, style, img, _ = _char_info(selected_name)
        portrait_update = gr.update(value=img, visible=img is not None)
        return desc, portrait_update

    def do_delete(selected_name):
        if not selected_name:
            return "**Select a character first.**", gr.update()
        get_library().remove(selected_name)
        choices = _char_choices()
        return f"Deleted **{selected_name}**.", gr.update(choices=choices, value=None)

    generate_btn.click(
        do_generate,
        inputs=[char_name, char_desc, char_style, char_provider, char_ref],
        outputs=[portrait_preview, gen_status, char_select],
    )

    save_btn.click(
        do_save,
        inputs=[char_name, char_desc, char_style],
        outputs=[gen_status, char_select],
    )

    load_btn.click(
        do_load,
        inputs=[char_select],
        outputs=[char_desc, char_style, char_ref, portrait_preview],
    )

    char_select.change(
        do_select,
        inputs=[char_select],
        outputs=[char_desc_view, portrait_preview],
    )

    delete_btn.click(
        do_delete,
        inputs=[char_select],
        outputs=[delete_msg, char_select],
    )
