#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHISPER_DIR="${ROOT_DIR}/vendor/whisper.cpp"

MODEL="base"
LANGUAGE="ja"
THREADS="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
STEP_MS="500"
LENGTH_MS="5000"
KEEP_MS="200"
CAPTURE_ID="-1"
OUTPUT_FILE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL="$2"
      shift 2
      ;;
    --language|-l)
      LANGUAGE="$2"
      shift 2
      ;;
    --threads|-t)
      THREADS="$2"
      shift 2
      ;;
    --step)
      STEP_MS="$2"
      shift 2
      ;;
    --length)
      LENGTH_MS="$2"
      shift 2
      ;;
    --keep)
      KEEP_MS="$2"
      shift 2
      ;;
    --capture|-c)
      CAPTURE_ID="$2"
      shift 2
      ;;
    --output|-o)
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --keep-context)
      EXTRA_ARGS+=("--keep-context")
      shift
      ;;
    --save-audio)
      EXTRA_ARGS+=("--save-audio")
      shift
      ;;
    --no-gpu)
      EXTRA_ARGS+=("--no-gpu")
      shift
      ;;
    --diarize)
      EXTRA_ARGS+=("--tinydiarize")
      MODEL="${MODEL}-tdrz"
      shift
      ;;
    --help|-h)
      cat <<USAGE
Usage: ./scripts/translate_stream.sh [options]

Options:
  --model MODEL       Whisper model name downloaded under vendor/whisper.cpp/models.
                      Example: tiny, base, small, medium
  --language LANG     Source language code. Default: ja
  --threads N         CPU threads. Default: detected CPU count
  --step MS           Capture step in milliseconds. Default: 500
  --length MS         Audio window length in milliseconds. Default: 5000
  --keep MS           Audio kept from previous chunk. Default: 200
  --capture ID        SDL capture device ID. Default: -1
  --output FILE       Also write translated text output to a file
  --keep-context      Keep prompt context between audio chunks
  --save-audio        Save recorded audio to a WAV file
  --no-gpu            Disable GPU inference
  --diarize           Enable speaker diarization (uses -tdrz model)
  --help              Show this help.

Example:
  ./scripts/translate_stream.sh --model base --language ja
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

BIN="${WHISPER_DIR}/build/bin/whisper-stream"
MODEL_PATH="${WHISPER_DIR}/models/ggml-${MODEL}.bin"

if [[ ! -x "${BIN}" || ! -f "${MODEL_PATH}" ]]; then
  echo "whisper.cpp stream binary or model is missing."
  echo "Run: ./whisper-translate setup ${MODEL}"
  exit 1
fi

CMD=(
  "${BIN}"
  -m "${MODEL_PATH}" \
  -t "${THREADS}" \
  --step "${STEP_MS}" \
  --length "${LENGTH_MS}" \
  --keep "${KEEP_MS}" \
  --capture "${CAPTURE_ID}" \
  --language "${LANGUAGE}" \
  --translate
)

if [[ -n "${OUTPUT_FILE}" ]]; then
  CMD+=(--file "${OUTPUT_FILE}")
fi

CMD+=("${EXTRA_ARGS[@]}")

exec "${CMD[@]}"
