#!/usr/bin/env python3
"""CLI: transcribe a local audio file and print JSON with timestamps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.audio import AudioError
from app.transcriber import get_transcriber


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file and emit text + segment timestamps."
    )
    parser.add_argument("audio", type=Path, help="Path to audio file (wav, mp3, ...)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON result",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON to stdout",
    )
    args = parser.parse_args()

    if not args.audio.exists():
        print(f"File not found: {args.audio}", file=sys.stderr)
        return 1

    try:
        result = get_transcriber().transcribe(args.audio)
    except AudioError as exc:
        print(f"Audio error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Transcription failed: {exc}", file=sys.stderr)
        return 3

    payload = result.model_dump()
    text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
