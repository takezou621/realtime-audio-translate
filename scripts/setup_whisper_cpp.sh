#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHISPER_DIR="${ROOT_DIR}/vendor/whisper.cpp"
MODEL="${1:-base}"

if [[ ! -d "${WHISPER_DIR}" ]]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required to fetch whisper.cpp."
    exit 1
  fi

  mkdir -p "${ROOT_DIR}/vendor"
  git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "${WHISPER_DIR}"
fi

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required. On macOS: brew install cmake"
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  if ! brew list sdl2 >/dev/null 2>&1; then
    echo "SDL2 is required for microphone streaming. Installing with Homebrew..."
    brew install sdl2
  fi
fi

cd "${WHISPER_DIR}"

if [[ ! -f "models/ggml-${MODEL}.bin" ]]; then
  ./models/download-ggml-model.sh "${MODEL}"
fi

cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j --config Release --target whisper-stream

echo
echo "Ready:"
echo "  ./whisper-translate run --model ${MODEL}"
