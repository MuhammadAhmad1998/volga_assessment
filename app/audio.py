"""Audio format conversion and long-file chunking."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import settings

SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".webm",
    ".aac",
    ".wma",
    ".mp4",  # audio track from video
}


class AudioError(Exception):
    """Raised when audio cannot be read or converted."""


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise AudioError(
            "ffmpeg is required for format conversion. "
            "Install it (e.g. `brew install ffmpeg`) and retry."
        )


def probe_duration(path: Path) -> float:
    """Return media duration in seconds using ffprobe."""
    ensure_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise AudioError(f"Could not probe duration for {path.name}: {exc}") from exc


def normalize_audio(input_path: Path, output_path: Path | None = None) -> Path:
    """
    Convert any supported input to 16 kHz mono WAV (Whisper-friendly).

    Different formats are handled uniformly by decoding through ffmpeg,
    which supports nearly all common codecs.
    """
    ensure_ffmpeg()
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise AudioError(
            f"Unsupported format '{input_path.suffix}'. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    if output_path is None:
        output_path = settings.upload_dir / f"{input_path.stem}_normalized.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        str(settings.target_channels),
        "-ar",
        str(settings.target_sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise AudioError(f"ffmpeg conversion failed: {exc.stderr[-500:]}") from exc

    return output_path


def split_into_chunks(
    wav_path: Path,
    chunk_seconds: float | None = None,
    overlap_seconds: float | None = None,
) -> list[tuple[Path, float]]:
    """
    Split a long WAV into overlapping chunks.

    Returns list of (chunk_path, start_offset_seconds).
    Short files return a single entry pointing at the original path.
    """
    ensure_ffmpeg()
    chunk_seconds = chunk_seconds or settings.chunk_seconds
    overlap_seconds = overlap_seconds or settings.chunk_overlap_seconds

    duration = probe_duration(wav_path)
    if duration <= chunk_seconds:
        return [(wav_path, 0.0)]

    step = max(chunk_seconds - overlap_seconds, 1.0)
    num_chunks = math.ceil((duration - overlap_seconds) / step)

    work_dir = Path(tempfile.mkdtemp(prefix="volga_chunks_"))
    chunks: list[tuple[Path, float]] = []

    for i in range(num_chunks):
        start = i * step
        out = work_dir / f"chunk_{i:04d}.wav"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{chunk_seconds:.3f}",
            "-i",
            str(wav_path),
            "-ac",
            str(settings.target_channels),
            "-ar",
            str(settings.target_sample_rate),
            "-c:a",
            "pcm_s16le",
            str(out),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        chunks.append((out, start))

    return chunks
