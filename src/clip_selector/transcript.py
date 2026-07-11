"""Transcript formatting and chunking for LLM processing."""
from typing import List, Optional

from ..transcribe import Segment, AudioEnergy

CHUNK_SECONDS = 20 * 60  # process transcript in ~20-minute windows


def segments_to_text(segments: List[Segment], energy: Optional[List[AudioEnergy]] = None) -> str:
    """Build enriched transcript with audio energy annotations interleaved."""
    if not energy:
        return "\n".join(f"[{s.start:.1f}s - {s.end:.1f}s] {s.text}" for s in segments)

    jumps = {i for i in range(1, len(energy)) if energy[i].rms_db - energy[i - 1].rms_db > 10}
    lines: List[str] = []
    energy_idx = 0

    for seg in segments:
        while energy_idx < len(energy) and energy[energy_idx].time <= seg.start:
            e = energy[energy_idx]
            if e.energy_level == "peak":
                lines.append(f"  🔊 PEAK at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
            elif e.energy_level == "loud":
                lines.append(f"  🔉 LOUD at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
            elif e.energy_level == "quiet":
                lines.append(f"  🔇 QUIET at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
            if energy_idx in jumps:
                jump_db = energy[energy_idx].rms_db - energy[energy_idx - 1].rms_db
                lines.append(f"  ⚡ ENERGY JUMP at {e.time:.1f}s (+{jump_db:.0f}dB sudden spike!)")
            energy_idx += 1
        lines.append(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")

    while energy_idx < len(energy):
        e = energy[energy_idx]
        if e.energy_level in ("peak", "loud"):
            lines.append(f"  🔊 {'PEAK' if e.energy_level == 'peak' else 'LOUD'} at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
        if energy_idx in jumps:
            jump_db = energy[energy_idx].rms_db - energy[energy_idx - 1].rms_db
            lines.append(f"  ⚡ ENERGY JUMP at {e.time:.1f}s (+{jump_db:.0f}dB)")
        energy_idx += 1

    return "\n".join(lines)


def chunk_segments(segments: List[Segment]) -> List[List[Segment]]:
    """Split segments into ~20-minute windows. Short videos use a single chunk."""
    if not segments:
        return []
    if segments[-1].end - segments[0].start <= CHUNK_SECONDS * 1.5:
        return [segments]

    chunks: List[List[Segment]] = []
    current: List[Segment] = []
    chunk_start = segments[0].start
    for seg in segments:
        if seg.start - chunk_start > CHUNK_SECONDS and current:
            chunks.append(current)
            current = []
            chunk_start = seg.start
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks
