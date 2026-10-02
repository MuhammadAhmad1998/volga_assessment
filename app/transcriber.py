"""Speech-to-text via faster-whisper, with optional mock mode for demos."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from app.audio import normalize_audio, probe_duration, split_into_chunks
from app.config import settings
from app.models import Segment, TranscriptionResult

logger = logging.getLogger(__name__)


class Transcriber:
    """
    Transcription engine.

    Set VOLGA_MOCK=1 to return deterministic mock segments without loading Whisper.
    Useful for CI / demos when the model weights are unavailable.
    """

    def __init__(self) -> None:
        self.mock = os.getenv("VOLGA_MOCK", "0") == "1"
        self._model = None

    @property
    def model(self):
        if self.mock:
            return None
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info(
                "Loading Whisper model=%s device=%s compute=%s",
                settings.whisper_model,
                settings.whisper_device,
                settings.whisper_compute_type,
            )
            self._model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        audio_path = Path(audio_path)
        normalized = normalize_audio(audio_path)
        duration = probe_duration(normalized)

        if self.mock:
            return self._mock_result(duration)

        chunks = split_into_chunks(normalized)
        all_segments: list[Segment] = []
        language: str | None = None
        seg_id = 0

        for chunk_path, offset in chunks:
            segments, info = self.model.transcribe(
                str(chunk_path),
                beam_size=5,
                word_timestamps=False,
                vad_filter=True,
            )
            if language is None:
                language = getattr(info, "language", None)

            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                all_segments.append(
                    Segment(
                        id=seg_id,
                        start=round(seg.start + offset, 3),
                        end=round(seg.end + offset, 3),
                        text=text,
                    )
                )
                seg_id += 1

        # Deduplicate near-overlap text at chunk boundaries
        all_segments = _dedupe_boundary_segments(all_segments)
        full_text = " ".join(s.text for s in all_segments).strip()

        return TranscriptionResult(
            language=language,
            duration_seconds=round(duration, 3),
            text=full_text,
            segments=all_segments,
        )

    def _mock_result(self, duration: float) -> TranscriptionResult:
        """Deterministic output so the pipeline is demoable without model download."""
        segments = [
            Segment(id=0, start=0.0, end=min(2.5, duration), text="Hello, this is a mock transcription."),
            Segment(
                id=1,
                start=min(2.5, duration),
                end=min(5.0, duration),
                text="The pipeline returns timestamps per segment.",
            ),
        ]
        if duration > 5:
            segments.append(
                Segment(
                    id=2,
                    start=5.0,
                    end=min(duration, 8.0),
                    text="Longer audio would continue with more segments.",
                )
            )
        text = " ".join(s.text for s in segments)
        return TranscriptionResult(
            language="en",
            duration_seconds=round(duration, 3),
            text=text,
            segments=segments,
        )


def _dedupe_boundary_segments(segments: list[Segment]) -> list[Segment]:
    """Drop near-duplicate segments caused by chunk overlap."""
    if not segments:
        return segments
    cleaned: list[Segment] = [segments[0]]
    for seg in segments[1:]:
        prev = cleaned[-1]
        same_text = seg.text.lower() == prev.text.lower()
        overlaps = seg.start < prev.end + 0.35
        if same_text and overlaps:
            continue
        cleaned.append(seg)
    # Re-number ids
    for i, seg in enumerate(cleaned):
        seg.id = i
    return cleaned


@lru_cache(maxsize=1)
def get_transcriber() -> Transcriber:
    return Transcriber()
