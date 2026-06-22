"""
Word-level transcription — two providers:

  TRANSCRIPTION_PROVIDER=groq  (default) — uploads audio to Groq's Whisper API,
      fast and free, no local GPU/CPU needed.

  TRANSCRIPTION_PROVIDER=local — runs faster-whisper locally, fully offline.
"""
import hashlib
import json
import os
import tempfile
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from .config import settings
from .cache import cache_get, cache_set


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)


def _extract_audio(video_path: str, out_path: str) -> None:
    """Extract audio to mp3 for Groq upload (much smaller than raw video)."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path!r}")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
         "-b:a", "64k", out_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, stderr=result.stderr.decode(errors="replace")
        )


def _transcribe_groq(video_path: str) -> List[Segment]:
    import httpx
    from groq import Groq
    client = Groq(
        api_key=settings.groq_api_key,
        timeout=httpx.Timeout(300.0, connect=30.0),
    )

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        audio_path = tmp.name

    try:
        print("   Extracting audio...")
        _extract_audio(video_path, audio_path)

        print("   Uploading to Groq Whisper...")
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model=settings.groq_whisper_model,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
            )
    finally:
        os.unlink(audio_path)

    # Groq returns word timestamps on response.words, not inside each segment.
    all_words = [
        Word(text=w["word"].strip(), start=w["start"], end=w["end"])
        for w in (response.words or [])
    ]

    result: List[Segment] = []
    for seg in response.segments or []:
        seg_start = seg["start"] if isinstance(seg, dict) else seg.start
        seg_end = seg["end"] if isinstance(seg, dict) else seg.end
        seg_text = seg["text"] if isinstance(seg, dict) else seg.text
        seg_words = [w for w in all_words if seg_start <= w.start <= seg_end]
        result.append(Segment(start=seg_start, end=seg_end, text=seg_text.strip(), words=seg_words))
    return result


def _transcribe_local(video_path: str) -> List[Segment]:
    from faster_whisper import WhisperModel
    model = WhisperModel(
        settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    segments, _info = model.transcribe(
        video_path,
        word_timestamps=True,
        vad_filter=True,
    )
    result: List[Segment] = []
    for seg in segments:
        words = [
            Word(text=w.word.strip(), start=w.start, end=w.end)
            for w in (seg.words or [])
        ]
        result.append(
            Segment(start=seg.start, end=seg.end, text=seg.text.strip(), words=words)
        )
    return result


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()[:16]


def _segments_to_json(segments: List[Segment]) -> str:
    return json.dumps([
        {"start": s.start, "end": s.end, "text": s.text,
         "words": [{"text": w.text, "start": w.start, "end": w.end} for w in s.words]}
        for s in segments
    ])


def _segments_from_json(raw: str) -> List[Segment]:
    data = json.loads(raw)
    return [
        Segment(
            start=s["start"], end=s["end"], text=s["text"],
            words=[Word(text=w["text"], start=w["start"], end=w["end"]) for w in s["words"]],
        )
        for s in data
    ]


def transcribe(video_path: str) -> List[Segment]:
    cache_key = _file_hash(video_path)
    cached = cache_get("transcribe", cache_key)
    if cached is not None:
        print("   Using cached transcription.")
        return _segments_from_json(cached)

    if settings.transcription_provider == "groq":
        segments = _transcribe_groq(video_path)
    elif settings.transcription_provider == "local":
        segments = _transcribe_local(video_path)
    else:
        raise ValueError(
            f"Unknown TRANSCRIPTION_PROVIDER: {settings.transcription_provider!r}. "
            "Use 'groq' or 'local'."
        )

    cache_set("transcribe", cache_key, _segments_to_json(segments))
    return segments
