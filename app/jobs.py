"""In-memory job store with retry tracking (demo-scale)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings
from app.models import JobStatus, TranscriptionResult


@dataclass
class Job:
    job_id: str
    filename: str
    audio_path: str
    status: JobStatus = JobStatus.pending
    result: Optional[TranscriptionResult] = None
    error: Optional[str] = None
    attempts: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, filename: str, audio_path: str) -> Job:
        job = Job(job_id=str(uuid.uuid4()), filename=filename, audio_path=audio_path)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())


job_store = JobStore()
MAX_RETRIES = settings.max_retries
