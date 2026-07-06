"""Settings tab — API keys and system configuration."""

import os
import gradio as gr

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ENV_FILE = os.path.join(_ROOT, ".env")


def _read_env() -> dict[str, str]:
    result = {}
    if not os.path.exists(_ENV_FILE):
        return result
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _write_env(updates: dict[str, str]):
    lines = []
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE) as f:
            lines = f.readlines()

    seen = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.partition("=")[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                seen.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in seen:
            new_lines.append(f"{k}={v}\n")

    with open(_ENV_FILE, "w") as f:
        f.writelines(new_lines)

    # Apply live — no restart needed
    from ...config import settings
    _ATTR_MAP = {
        "LLM_PROVIDER": "llm_provider",
        "GROQ_API_KEY": "groq_api_key",
        "GROQ_MODEL": "groq_model",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "ANTHROPIC_MODEL": "anthropic_model",
        "TRANSCRIPTION_PROVIDER": "transcription_provider",
        "GROQ_WHISPER_MODEL": "groq_whisper_model",
        "GEMINI_API_KEY": "gemini_api_key",
        "OUTPUT_DIR": "output_dir",
    }
    for k, v in updates.items():
        os.environ[k] = v
        attr = _ATTR_MAP.get(k)
        if attr:
            setattr(settings, attr, v)


def create_settings_tab():
    gr.Markdown("Changes are written to `.env` and applied immediately — no restart needed.")

    env = _read_env()

    with gr.Row():
        with gr.Column():
            gr.Markdown("### LLM")
            llm_provider = gr.Radio(
                label="LLM Provider",
                choices=["groq", "anthropic"],
                value=env.get("LLM_PROVIDER", "groq"),
            )
            groq_api_key = gr.Textbox(
                label="Groq API Key", value=env.get("GROQ_API_KEY", ""),
                type="password", placeholder="gsk_...",
            )
            groq_model = gr.Textbox(
                label="Groq Model", value=env.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                placeholder="llama-3.3-70b-versatile",
            )
            anthropic_api_key = gr.Textbox(
                label="Anthropic API Key", value=env.get("ANTHROPIC_API_KEY", ""),
                type="password", placeholder="sk-ant-...",
            )
            anthropic_model = gr.Textbox(
                label="Anthropic Model", value=env.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                placeholder="claude-sonnet-4-6",
            )

        with gr.Column():
            gr.Markdown("### Voice")
            elevenlabs_api_key = gr.Textbox(
                label="ElevenLabs API Key", value=env.get("ELEVENLABS_API_KEY", ""),
                type="password", placeholder="sk_...",
            )

            gr.Markdown("### Transcription")
            transcription_provider = gr.Radio(
                label="Transcription Provider",
                choices=["groq", "local"],
                value=env.get("TRANSCRIPTION_PROVIDER", "groq"),
            )
            groq_whisper_model = gr.Textbox(
                label="Groq Whisper Model", value=env.get("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"),
                placeholder="whisper-large-v3-turbo",
            )

    with gr.Row():
        with gr.Column():
            gr.Markdown("### Image / Video Generation")
            openai_api_key = gr.Textbox(
                label="OpenAI API Key", value=env.get("OPENAI_API_KEY", ""),
                type="password", placeholder="sk-...",
            )
            openai_image_model = gr.Textbox(
                label="OpenAI Image Model", value=env.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                placeholder="gpt-image-1",
            )
            gemini_api_key = gr.Textbox(
                label="Gemini / Veo API Key", value=env.get("GEMINI_API_KEY", ""),
                type="password", placeholder="AIza...",
            )
            sd_api_url = gr.Textbox(
                label="Stable Diffusion API URL", value=env.get("SD_API_URL", "http://127.0.0.1:7860"),
                placeholder="http://127.0.0.1:7860",
            )

        with gr.Column():
            gr.Markdown("### Stock Media")
            pexels_api_key = gr.Textbox(
                label="Pexels API Key", value=env.get("PEXELS_API_KEY", ""),
                type="password", placeholder="pexels_...",
            )

            gr.Markdown("### Output")
            output_dir = gr.Textbox(
                label="Output Directory", value=env.get("OUTPUT_DIR", "output"),
                placeholder="output",
            )

    save_btn = gr.Button("Save", variant="primary", size="lg")
    status = gr.Markdown("")

    def _save(
        llm_prov, groq_key, groq_mod, ant_key, ant_mod,
        el_key, trans_prov, whisper_mod,
        oai_key, oai_img_mod, gem_key, sd_url,
        pex_key, out_dir,
    ):
        _write_env({
            "LLM_PROVIDER": llm_prov or "groq",
            "GROQ_API_KEY": groq_key or "",
            "GROQ_MODEL": groq_mod or "llama-3.3-70b-versatile",
            "ANTHROPIC_API_KEY": ant_key or "",
            "ANTHROPIC_MODEL": ant_mod or "claude-sonnet-4-6",
            "ELEVENLABS_API_KEY": el_key or "",
            "TRANSCRIPTION_PROVIDER": trans_prov or "groq",
            "GROQ_WHISPER_MODEL": whisper_mod or "whisper-large-v3-turbo",
            "OPENAI_API_KEY": oai_key or "",
            "OPENAI_IMAGE_MODEL": oai_img_mod or "gpt-image-1",
            "GEMINI_API_KEY": gem_key or "",
            "SD_API_URL": sd_url or "http://127.0.0.1:7860",
            "PEXELS_API_KEY": pex_key or "",
            "OUTPUT_DIR": out_dir or "output",
        })
        return gr.update(value="**Saved.** Changes are active immediately.")

    save_btn.click(
        _save,
        inputs=[
            llm_provider, groq_api_key, groq_model, anthropic_api_key, anthropic_model,
            elevenlabs_api_key, transcription_provider, groq_whisper_model,
            openai_api_key, openai_image_model, gemini_api_key, sd_api_url,
            pexels_api_key, output_dir,
        ],
        outputs=[status],
    )
