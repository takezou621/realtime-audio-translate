#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEXT="${1:-Good morning everyone. The project status looks good. We need to finish the budget review by Friday and send the final report to the customer.}"
MODEL="${MODEL:-base}"
OUT_DIR="${ROOT_DIR}/test_audio"
AIFF="${OUT_DIR}/teams_test.aiff"
WAV="${OUT_DIR}/teams_test.wav"
TRANSCRIPT="${OUT_DIR}/teams_test.en.txt"
TRANSLATION="${OUT_DIR}/teams_test.ja.txt"

mkdir -p "${OUT_DIR}"

say -v Samantha -o "${AIFF}" "${TEXT}"
ffmpeg -y -hide_banner -loglevel error -i "${AIFF}" -ar 16000 -ac 1 "${WAV}"

"${ROOT_DIR}/vendor/whisper.cpp/build/bin/whisper-cli" \
  -m "${ROOT_DIR}/vendor/whisper.cpp/models/ggml-${MODEL}.bin" \
  -f "${WAV}" \
  -l en \
  -nt \
  -np \
  > "${TRANSCRIPT}"

python3 - "${TRANSCRIPT}" "${TRANSLATION}" <<'PY'
import os
import sys
from pathlib import Path

from scripts.teams_translate import ROOT_DIR, load_env_file, translate_openai

transcript_path = Path(sys.argv[1])
translation_path = Path(sys.argv[2])
text = transcript_path.read_text(encoding="utf-8").strip()
load_env_file(ROOT_DIR / ".env")

if os.environ.get("OPENAI_API_KEY"):
    translation = translate_openai(text, "Japanese", os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
else:
    # Deterministic fixture translation for local smoke tests when API credentials
    # are not available. Live Teams translation still uses OpenAI.
    translation = (
        "皆さん、おはようございます。プロジェクトの状況は順調です。"
        "金曜日までに予算レビューを終え、最終報告書を顧客に送る必要があります。"
    )

translation_path.write_text(translation + "\n", encoding="utf-8")
print("EN:", text)
print("JA:", translation)
PY

echo
echo "Files:"
echo "  ${WAV}"
echo "  ${TRANSCRIPT}"
echo "  ${TRANSLATION}"
