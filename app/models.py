from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Segment(BaseModel):
    """A transcribed speech segment with timestamps."""

    id: int
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str


class TranscriptionResult(BaseModel):
    """Full transcription payload returned to clients."""

    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    text: str
    segments: list[Segment]


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    filename: Optional[str] = None
    result: Optional[TranscriptionResult] = None
    error: Optional[str] = None
    attempts: int = 0


class HealthResponse(BaseModel):
    status: str
    model: str
    version: str
