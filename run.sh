#!/usr/bin/env bash
# Volga — one-command setup & demo for interviewers
# Usage:
#   ./run.sh              Install deps + transcribe sample (CLI)
#   ./run.sh api          Start the HTTP API on :8000
#   ./run.sh test-api     Start API briefly and curl a live request
#   ./run.sh mock         Fast offline demo (no Whisper download)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"
PORT="${PORT:-8000}"
SAMPLE="$ROOT/samples/speech.wav"
export VOLGA_WHISPER_MODEL="${VOLGA_WHISPER_MODEL:-tiny}"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
CYAN=$'\033[0;36m'
NC=$'\033[0m'

info()  { echo "${CYAN}==>${NC} $*"; }
ok()    { echo "${GREEN}OK${NC}  $*"; }
fail()  { echo "${RED}ERROR:${NC} $*" >&2; exit 1; }

usage() {
  cat <<EOF
Volga Transcription Pipeline

Commands:
  ./run.sh              Setup + CLI transcription of samples/speech.wav
  ./run.sh api          Setup + start API at http://localhost:${PORT}
  ./run.sh test-api     Setup + API smoke test (upload sample, print JSON)
  ./run.sh mock         Setup + fast offline CLI demo (no model download)

Optional env:
  VOLGA_WHISPER_MODEL=tiny|base|small   (default: tiny)
  PORT=8000
  PYTHON=python3
EOF
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "'$1' is required. $2"
}

ensure_sample() {
  mkdir -p "$ROOT/samples"
  if [[ -f "$SAMPLE" ]]; then
    return 0
  fi
  info "samples/speech.wav missing — generating a short spoken sample..."
  if command -v say >/dev/null 2>&1; then
    local tmp="/tmp/volga_speech_$$.aiff"
    say -o "$tmp" \
      "Hello, this is a real speech sample for the transcription pipeline. It returns text with timestamps per segment."
    ffmpeg -y -i "$tmp" -ac 1 -ar 16000 "$SAMPLE" >/dev/null 2>&1
    rm -f "$tmp"
    ok "Created $SAMPLE"
  else
    fail "No samples/speech.wav found and 'say' is unavailable.
Place any short English speech file at samples/speech.wav and re-run."
  fi
}

setup() {
  need_cmd "$PYTHON" "Install Python 3.10+."
  need_cmd ffmpeg "Install ffmpeg (macOS: brew install ffmpeg)."
  need_cmd ffprobe "Install ffmpeg (includes ffprobe)."

  if [[ ! -d "$VENV" ]]; then
    info "Creating virtualenv at .venv ..."
    "$PYTHON" -m venv "$VENV"
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"

  info "Installing Python dependencies..."
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
  ok "Environment ready (model=${VOLGA_WHISPER_MODEL})"
}

run_cli() {
  setup
  ensure_sample
  unset VOLGA_MOCK || true
  info "Transcribing $SAMPLE (first run may download the Whisper model)..."
  python cli.py "$SAMPLE" --pretty
  ok "CLI demo finished"
}

run_mock() {
  setup
  ensure_sample
  export VOLGA_MOCK=1
  info "Running offline mock transcription..."
  python cli.py "$SAMPLE" --pretty
  ok "Mock demo finished"
}

run_api() {
  setup
  ensure_sample
  unset VOLGA_MOCK || true
  info "API docs: http://localhost:${PORT}/docs"
  info "Health:    http://localhost:${PORT}/health"
  info "Example:   curl -F file=@samples/speech.wav http://localhost:${PORT}/v1/transcribe/sync"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
}

run_test_api() {
  setup
  ensure_sample
  unset VOLGA_MOCK || true

  info "Starting API on port ${PORT}..."
  uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >/tmp/volga_api.log 2>&1 &
  API_PID=$!
  cleanup() {
    if [[ -n "${API_PID:-}" ]]; then
      kill "$API_PID" >/dev/null 2>&1 || true
    fi
  }
  trap cleanup EXIT

  for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null; then
      break
    fi
    sleep 1
  done
  curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null || fail "API did not become healthy. See /tmp/volga_api.log"

  info "POST /v1/transcribe/sync ..."
  curl -s -F "file=@${SAMPLE}" "http://127.0.0.1:${PORT}/v1/transcribe/sync" | python -m json.tool
  ok "API smoke test finished"
}

cmd="${1:-demo}"
case "$cmd" in
  -h|--help|help) usage ;;
  demo|"")        run_cli ;;
  mock)           run_mock ;;
  api)            run_api ;;
  test-api)       run_test_api ;;
  *)              fail "Unknown command: $cmd (try ./run.sh --help)" ;;
esac
