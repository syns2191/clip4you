import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # LLM provider: "anthropic" or "groq"
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Transcription provider: "groq" (cloud, fast, free) or "local" (faster-whisper, offline)
    transcription_provider: str = os.getenv("TRANSCRIPTION_PROVIDER", "groq")
    groq_whisper_model: str = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

    # faster-whisper settings (only used when TRANSCRIPTION_PROVIDER=local)
    whisper_model_size: str = os.getenv("WHISPER_MODEL_SIZE", "medium")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "auto")  # cpu / cuda / auto
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "auto")

    output_dir: str = os.getenv("OUTPUT_DIR", "output")

    clip_min_seconds: int = int(os.getenv("CLIP_MIN_SECONDS", "60"))
    clip_max_seconds: int = int(os.getenv("CLIP_MAX_SECONDS", "90"))

    vertical_width: int = 1080
    vertical_height: int = 1920


settings = Settings()
