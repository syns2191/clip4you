"""
Word-level transcription — two providers:

  TRANSCRIPTION_PROVIDER=groq  (default) — uploads audio to Groq's Whisper API,
      fast and free, no local GPU/CPU needed.

  TRANSCRIPTION_PROVIDER=local — runs faster-whisper locally, fully offline.
"""
import hashlib
import io
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


def _groq_whisper_upload(audio_path: str) -> List[Segment]:
    """Upload an audio file to Groq Whisper and parse the response into Segments."""
    import httpx
    from groq import Groq
    client = Groq(
        api_key=settings.groq_api_key,
        timeout=httpx.Timeout(300.0, connect=30.0),
    )

    file_size = os.path.getsize(audio_path)
    print(f"   Uploading to Groq Whisper ({file_size / 1024 / 1024:.1f} MB)...")
    with open(audio_path, "rb") as f:

        class _ProgressFile(io.RawIOBase):
            def __init__(self, fobj, total):
                self._f = fobj
                self._total = total
                self._uploaded = 0
                self.name = fobj.name

            def readinto(self, b):
                data = self._f.read(len(b))
                if not data:
                    return 0
                n = len(data)
                b[:n] = data
                self._uploaded += n
                pct = self._uploaded / self._total * 100
                print(f"\r   Upload progress: {pct:5.1f}%", end="", flush=True)
                return n

            def readable(self):
                return True

        pf = _ProgressFile(f, file_size)
        response = client.audio.transcriptions.create(
            model=settings.groq_whisper_model,
            file=(os.path.basename(audio_path), pf, "audio/mpeg"),
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
        )
        print()

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


def _transcribe_groq(video_path: str) -> List[Segment]:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        audio_path = tmp.name
    try:
        print("   Extracting audio...")
        _extract_audio(video_path, audio_path)
        return _groq_whisper_upload(audio_path)
    finally:
        os.unlink(audio_path)


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


@dataclass
class AudioEnergy:
    """Audio loudness measurement for a time window."""
    time: float
    rms_db: float
    peak_db: float
    is_spike: bool = False
    energy_level: str = "normal"  # quiet, normal, loud, peak


def _energy_to_json(energy: List[AudioEnergy]) -> str:
    return json.dumps([
        {"time": e.time, "rms_db": e.rms_db, "peak_db": e.peak_db,
         "is_spike": e.is_spike, "energy_level": e.energy_level}
        for e in energy
    ])


def _energy_from_json(raw: str) -> List[AudioEnergy]:
    return [
        AudioEnergy(
            time=e["time"], rms_db=e["rms_db"], peak_db=e["peak_db"],
            is_spike=e["is_spike"], energy_level=e["energy_level"],
        )
        for e in json.loads(raw)
    ]


def analyze_audio_energy(
    video_path: str,
    window_seconds: float = 2.0,
) -> List[AudioEnergy]:
    """Analyze audio energy in a single ffmpeg pass using astats with reset.
    Returns one measurement per time window with spike detection."""
    from .render import FFMPEG

    cache_key = _file_hash(video_path) + f"_energy_{window_seconds}"
    cached = cache_get("audio_energy", cache_key)
    if cached is not None:
        return _energy_from_json(cached)

    # reset=1 gives per-frame stats; we bucket them in Python by window
    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-af", "astats=metadata=1:reset=1,ametadata=print",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse ametadata output from stderr.
    # Format per frame group:
    #   frame:N  pts:X  pts_time:T
    #   lavfi.astats.1.RMS_level=-23.45
    #   lavfi.astats.1.Peak_level=-17.15
    #   lavfi.astats.Overall.RMS_level=-23.45
    #   lavfi.astats.Overall.Peak_level=-17.15
    # We collect Overall.RMS_level and Overall.Peak_level per pts_time,
    # then keep one measurement per window.
    raw_points: List[tuple] = []  # (time, rms, peak)
    current_time = 0.0
    current_rms = -60.0
    current_peak = -60.0

    for line in result.stderr.split("\n"):
        line = line.strip()
        if "pts_time:" in line:
            try:
                current_time = float(line.split("pts_time:")[-1].strip())
            except (ValueError, IndexError):
                pass
        elif "Overall.RMS_level=" in line:
            try:
                val = line.split("=")[-1].strip()
                current_rms = float(val) if val not in ("-inf", "inf") else -60.0
            except (ValueError, IndexError):
                pass
        elif "Overall.Peak_level=" in line:
            try:
                val = line.split("=")[-1].strip()
                current_peak = float(val) if val not in ("-inf", "inf") else -60.0
            except (ValueError, IndexError):
                pass
            raw_points.append((current_time, current_rms, current_peak))
            current_rms = -60.0
            current_peak = -60.0

    if not raw_points:
        return []

    # Bucket into windows — average the RMS within each window
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for t, rms, peak in raw_points:
        bucket = int(t / window_seconds) * window_seconds
        buckets[bucket].append((rms, peak))

    measurements: List[AudioEnergy] = []
    for bucket_time in sorted(buckets.keys()):
        points = buckets[bucket_time]
        valid_rms = [r for r, _ in points if r > -59]
        valid_peak = [p for _, p in points if p > -59]
        avg_rms = sum(valid_rms) / len(valid_rms) if valid_rms else -60.0
        max_peak = max(valid_peak) if valid_peak else -60.0
        measurements.append(AudioEnergy(
            time=bucket_time,
            rms_db=round(avg_rms, 1),
            peak_db=round(max_peak, 1),
        ))

    if len(measurements) < 3:
        return measurements

    # Classify energy levels relative to the video's average
    rms_values = [m.rms_db for m in measurements if m.rms_db > -59]
    if not rms_values:
        return measurements
    avg_rms = sum(rms_values) / len(rms_values)

    for m in measurements:
        diff = m.rms_db - avg_rms
        if diff > 8:
            m.energy_level = "peak"
            m.is_spike = True
        elif diff > 4:
            m.energy_level = "loud"
            m.is_spike = True
        elif diff < -8:
            m.energy_level = "quiet"
        else:
            m.energy_level = "normal"

    # Detect sudden jumps (quiet→loud = most engaging moments)
    for i in range(1, len(measurements)):
        prev = measurements[i - 1]
        curr = measurements[i]
        jump = curr.rms_db - prev.rms_db
        if jump > 10:
            curr.is_spike = True
            curr.energy_level = "peak"

    cache_set("audio_energy", cache_key, _energy_to_json(measurements))
    return measurements


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


def transcribe_audio(audio_path: str) -> List[Segment]:
    """Transcribe an audio file (MP3, WAV, etc.) directly — no video extraction step."""
    cache_key = _file_hash(audio_path)
    cached = cache_get("transcribe_audio", cache_key)
    if cached is not None:
        print("   Using cached audio transcription.")
        return _segments_from_json(cached)

    if settings.transcription_provider == "groq":
        segments = _groq_whisper_upload(audio_path)
    elif settings.transcription_provider == "local":
        segments = _transcribe_local(audio_path)
    else:
        raise ValueError(
            f"Unknown TRANSCRIPTION_PROVIDER: {settings.transcription_provider!r}. "
            "Use 'groq' or 'local'."
        )

    cache_set("transcribe_audio", cache_key, _segments_to_json(segments))
    return segments
