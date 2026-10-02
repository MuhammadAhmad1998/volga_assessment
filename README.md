# Volga — Speech-to-Text Transcription Pipeline

Accept an audio file → transcribe speech to text → return **full text + timestamps per segment**.

Built with **Python**, **FastAPI**, **faster-whisper** (OpenAI Whisper), and **ffmpeg**.

---

## For interviewers — run this

**Requirements:** Python 3.10+, [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` on macOS)

```bash
chmod +x run.sh
./run.sh
```

That installs dependencies into `.venv` and prints a JSON transcription of `samples/speech.wav`.

| Command | What it does |
|---|---|
| `./run.sh` | Setup + CLI transcription (real Whisper) |
| `./run.sh test-api` | Setup + live API upload smoke test |
| `./run.sh api` | Start API at http://localhost:8000 (docs at `/docs`) |
| `./run.sh mock` | Offline demo without downloading a model |

First real Whisper run downloads a small model (`tiny`) — usually 1–2 minutes. Later runs are faster.

Transcribe your own file:

```bash
source .venv/bin/activate
python cli.py /path/to/audio.mp3 --pretty
```

---

## Requirements checklist

| Requirement | How this project meets it |
|---|---|
| Accept audio file (WAV/MP3/…) | CLI path arg or `POST /v1/transcribe` multipart upload |
| Transcribe speech → text | `faster-whisper` ASR engine |
| Return timestamps per segment | JSON `segments[{id,start,end,text}]` |
| Different audio formats | ffmpeg normalizes all inputs to 16 kHz mono WAV |
| Long audio files | Split into overlapping chunks; merge timestamps with offsets |
| Concurrent uploads (design) | Async jobs + queue/workers — see below |
| Storage (design) | S3 + Postgres — see below |
| Retry/recover (design) | Job state machine + retries — see below |
| Expose as API (design + demo) | FastAPI endpoints implemented |

---

## API

Start: `./run.sh api` → http://localhost:8000/docs

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `POST` | `/v1/transcribe` | Upload → async job (`202` + `job_id`) |
| `GET` | `/v1/jobs/{id}` | Poll status / result |
| `POST` | `/v1/transcribe/sync` | Blocking transcription (short demos) |

Example:

```bash
curl -F "file=@samples/speech.wav" http://localhost:8000/v1/transcribe/sync
```

Example response:

```json
{
  "status": "completed",
  "result": {
    "language": "en",
    "duration_seconds": 7.1,
    "text": "Hello, this is a real speech sample...",
    "segments": [
      {"id": 0, "start": 0.0, "end": 4.4, "text": "Hello, this is a real speech sample..."},
      {"id": 1, "start": 4.4, "end": 7.0, "text": "It returns text with timestamps per segment."}
    ]
  }
}
```

---

## Project layout

```
volga/
├── run.sh                 # One-command setup & demo
├── cli.py                 # CLI transcription
├── app/
│   ├── main.py            # FastAPI service
│   ├── audio.py           # Format conversion + long-file chunking
│   ├── transcriber.py     # Whisper engine
│   ├── jobs.py            # In-memory jobs + retries
│   ├── models.py          # Response schemas
│   └── config.py
├── samples/speech.wav     # Short spoken English sample
├── FORM_ANSWERS.md        # Paste-ready design answers (Google Form)
├── requirements.txt
└── README.md
```

---

## Design answers (Part 1 & 2)

### How different audio formats are handled

Every file is converted with **ffmpeg** to a canonical **16 kHz mono PCM WAV**. MP3, M4A, FLAC, OGG, WebM, etc. share one ASR path after conversion. Unsupported extensions are rejected with HTTP 400.

### How long audio files are handled

Files longer than ~5 minutes are split into **overlapping chunks**. Each chunk is transcribed; segment times are shifted by the chunk offset and near-duplicates at boundaries are removed. Short files skip chunking.

### Concurrent uploads

API accepts the file, stores it, enqueues a job, returns `202` + `job_id`. Workers (Celery/RQ + Redis/SQS in production) run ASR with a concurrency limit. Return `429` when the queue is full. Scale API for IO and workers for GPU/CPU separately.

### Storage

- Audio → object storage (S3/GCS) with lifecycle expiry  
- Job metadata → Postgres  
- Transcript JSON → Postgres JSONB and/or S3 object + DB pointer  

### Retry / recovery

State machine: `pending → processing → completed | failed`. Retry transient errors with backoff (max attempts, same `job_id`). Persist last error. Reclaim stuck `processing` jobs after a lease timeout. Failed jobs can be replayed.

### API exposure

REST + OpenAPI (this repo). Production extras: auth, signed direct uploads, webhooks on completion, rate limits.

More copy-paste answers: [`FORM_ANSWERS.md`](FORM_ANSWERS.md).

---

## Config

| Env | Default | Meaning |
|---|---|---|
| `VOLGA_WHISPER_MODEL` | `tiny` | Whisper size |
| `VOLGA_WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `VOLGA_CHUNK_SECONDS` | `300` | Long-file split size |
| `VOLGA_MAX_RETRIES` | `3` | Job retry budget |
| `VOLGA_MOCK` | `0` | `1` = offline fake transcript |

---

## License

MIT — interview / assignment use.
