"""FastAPI service: upload audio → async transcription job → poll for result."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app import __version__
from app.audio import SUPPORTED_EXTENSIONS, AudioError
from app.config import settings
from app.jobs import MAX_RETRIES, Job, job_store
from app.models import HealthResponse, JobResponse, JobStatus
from app.transcriber import get_transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Volga Transcription API",
    description="Speech-to-text pipeline with per-segment timestamps.",
    version=__version__,
)


def _to_response(job: Job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        filename=job.filename,
        result=job.result,
        error=job.error,
        attempts=job.attempts,
    )


def process_job(job_id: str) -> None:
    """Worker entrypoint: transcribe with bounded retries."""
    job = job_store.get(job_id)
    if job is None:
        return

    with job.lock:
        if job.status == JobStatus.completed:
            return
        job.status = JobStatus.processing

    transcriber = get_transcriber()

    while True:
        with job.lock:
            job.attempts += 1
            attempt = job.attempts

        try:
            logger.info("Job %s attempt %s: %s", job_id, attempt, job.filename)
            result = transcriber.transcribe(Path(job.audio_path))
            with job.lock:
                job.result = result
                job.status = JobStatus.completed
                job.error = None
            logger.info("Job %s completed (%s segments)", job_id, len(result.segments))
            return
        except Exception as exc:  # noqa: BLE001 — surface any engine failure as job error
            logger.exception("Job %s failed on attempt %s", job_id, attempt)
            with job.lock:
                job.error = str(exc)
                if attempt >= MAX_RETRIES:
                    job.status = JobStatus.failed
                    return
                # Loop to retry


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model=settings.whisper_model, version=__version__)


@app.post("/v1/transcribe", response_model=JobResponse, status_code=202)
async def create_transcription(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Audio file (wav, mp3, m4a, flac, ogg, ...)"),
) -> JobResponse:
    """
    Accept an audio upload and start an async transcription job.

    Poll GET /v1/jobs/{job_id} until status is completed or failed.
    """
    suffix = Path(file.filename or "audio.bin").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    dest = settings.upload_dir / f"{uuid4().hex}{suffix}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()

    job = job_store.create(filename=file.filename or dest.name, audio_path=str(dest))
    background_tasks.add_task(process_job, job.job_id)
    return _to_response(job)


@app.post("/v1/transcribe/sync", response_model=JobResponse)
async def create_transcription_sync(
    file: UploadFile = File(...),
) -> JobResponse:
    """Synchronous helper for short clips / demos (blocks until done)."""
    suffix = Path(file.filename or "audio.bin").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{suffix}'")

    dest = settings.upload_dir / f"{uuid4().hex}{suffix}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()

    job = job_store.create(filename=file.filename or dest.name, audio_path=str(dest))
    try:
        process_job(job.job_id)
    except AudioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    refreshed = job_store.get(job.job_id)
    assert refreshed is not None
    if refreshed.status == JobStatus.failed:
        return JSONResponse(status_code=500, content=_to_response(refreshed).model_dump())
    return _to_response(refreshed)


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job)


@app.get("/v1/jobs", response_model=list[JobResponse])
def list_jobs() -> list[JobResponse]:
    return [_to_response(j) for j in job_store.list_jobs()]


# Warm the model in a background thread so the first request is faster.
@app.on_event("startup")
def warm_model() -> None:
    def _load() -> None:
        try:
            get_transcriber().model
        except Exception:  # noqa: BLE001
            logger.warning("Model warm-up skipped / failed (ok in mock mode)")

    threading.Thread(target=_load, daemon=True).start()
