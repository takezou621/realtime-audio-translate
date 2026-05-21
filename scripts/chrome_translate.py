#!/usr/bin/env python3
"""Capture Chrome system audio via BlackHole and translate in real-time."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT_DIR / ".env"

WHISPER_API = "https://api.openai.com/v1/audio/transcriptions"
CHAT_API = "https://api.openai.com/v1/chat/completions"
CHUNK_SEC = 5
SAMPLE_RATE = 44100

SPEAKER_LABELS = ["話者A", "話者B"]


def load_env(path: Path = DEFAULT_ENV) -> None:
    if not path.exists():
        return
    for raw in path.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip("\"'")
        os.environ.setdefault(k, v)


def err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def get_current_output_device_uid() -> str | None:
    """Return the UID of the current macOS sound output device, or None on failure."""
    try:
        r = subprocess.run(
            ["SwitchAudioSource", "-t", "output", "-c", "-f", "json"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout.strip())
        return data.get("uid")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def find_device_uid(name_substring: str) -> str | None:
    """Find the UID of an output device whose name contains *name_substring*.

    Also tries common localized equivalents for multi-output devices.
    """
    r = subprocess.run(
        ["SwitchAudioSource", "-a", "-t", "output", "-f", "json"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    # Build search list: user string + common localized names
    search_terms = [name_substring]
    if name_substring.lower() in ("multi-output device", "multi-output"):
        search_terms.append("複数出力装置")
    elif name_substring in ("複数出力装置",):
        search_terms.append("Multi-Output Device")
    for line in r.stdout.strip().splitlines():
        try:
            dev = json.loads(line)
            dev_name = dev.get("name", "")
            for term in search_terms:
                if term in dev_name:
                    return dev["uid"]
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def switch_output_device_by_uid(uid: str) -> bool:
    """Switch macOS sound output to the device with *uid*. Returns True on success."""
    r = subprocess.run(
        ["SwitchAudioSource", "-t", "output", "-u", uid],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def find_blackhole_device() -> str:
    r = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True,
    )
    in_audio = False
    for line in r.stderr.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio = True
            continue
        if in_audio and line.strip().startswith("["):
            # Format: [AVFoundation ...] [N] Device Name
            bracket = line.split("]")
            for part in bracket:
                part = part.strip()
                if part.startswith("[") and part[1:].isdigit():
                    idx = part[1:]
                elif "BlackHole" in part:
                    return f":{idx}"
    err("BlackHole not found in AVFoundation devices, using default.")
    return ":1"


def transcribe(audio_path: str, api_key: str, lang: str = "en", diarize: bool = False) -> tuple[str, list[dict]]:
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    response_format = "verbose_json" if diarize else "json"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="chunk.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n".encode()
        + audio_data
        + f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"whisper-1\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\n'
        f"{lang}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        f"{response_format}\r\n"
        f"--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        WHISPER_API,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("text", "").strip(), data.get("segments", [])
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        err(f"Whisper API error {e.code}: {detail}")
        return "", []


def detect_speakers(segments: list[dict], gap_threshold: float = 0.8) -> list[tuple[str, str]]:
    """Detect speaker turns based on gaps between segments."""
    if not segments:
        return []
    result = []
    speaker_idx = 0
    for i, seg in enumerate(segments):
        if i > 0:
            prev_end = segments[i - 1]["end"]
            curr_start = seg["start"]
            if curr_start - prev_end >= gap_threshold:
                speaker_idx += 1
        text = seg.get("text", "").strip()
        if text:
            result.append((SPEAKER_LABELS[speaker_idx % len(SPEAKER_LABELS)], text))
    return result


def translate(text: str, target: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    if not text:
        return ""
    has_speaker = any(text.startswith(f"{s}:") or text.startswith(f"{s}：") for s in SPEAKER_LABELS)
    if has_speaker:
        system_content = (
            f"Translate to natural {target}. "
            "Preserve the speaker label (話者A/話者B) at the start of the line. "
            "Return only the translation. Preserve names, numbers, and technical terms."
        )
    else:
        system_content = (
            f"Translate to natural {target}. "
            "Return only the translation. Preserve names, numbers, and technical terms."
        )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        CHAT_API,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        err(f"Translation API error {e.code}: {detail}")
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-time Chrome audio translator")
    parser.add_argument("--source-language", default="en", help="Source language code")
    parser.add_argument("--target-language", default="Japanese", help="Target language")
    parser.add_argument("--openai-model", default="gpt-4o-mini", help="Translation model")
    parser.add_argument("--chunk-seconds", type=int, default=CHUNK_SEC)
    parser.add_argument("--no-translate", action="store_true", help="Show transcript only")
    parser.add_argument("--diarize", action="store_true", help="Enable speaker detection")
    parser.add_argument("--output", "-o", default="", help="output file path (default: output/chrome_YYYYMMDD_HHMMSS.txt)")
    parser.add_argument("--device", default="", help="FFmpeg audio device (auto-detect if empty)")
    parser.add_argument(
        "--multi-output", default="Multi-Output Device",
        help="Name of the macOS multi-output device to switch to (default: 'Multi-Output Device')",
    )
    parser.add_argument(
        "--no-switch-device", action="store_true",
        help="Disable automatic audio output device switching",
    )
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        err("OPENAI_API_KEY not set. Add it to .env")
        return 1

    # --- audio output device switching ---
    original_device_uid = None
    if not args.no_switch_device:
        original_device_uid = get_current_output_device_uid()
        if original_device_uid is None:
            err(
                "SwitchAudioSource not found or failed. Install with:\n"
                "  brew install switchaudio-osx\n"
                "Continuing without automatic device switching."
            )
        else:
            target_uid = find_device_uid(args.multi_output)
            if target_uid is None:
                err(
                    f"Could not find output device matching '{args.multi_output}'. "
                    "Create one in Audio MIDI Setup (BlackHole + speakers).\n"
                    "Continuing with current device."
                )
                original_device_uid = None
            elif not switch_output_device_by_uid(target_uid):
                err(
                    f"Could not switch to '{args.multi_output}'. "
                    "Continuing with current device."
                )
                original_device_uid = None
            else:
                err(f"Switched output to: {args.multi_output}")

    device = args.device or find_blackhole_device()
    err(f"Capturing from device: {device}")
    err(f"Chunk size: {args.chunk_seconds}s | Source: {args.source_language} | Target: {args.target_language}")

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = ROOT_DIR / "output" / f"chrome_{timestamp}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_file = output_path.open("a", encoding="utf-8")
    err(f"Saving translations to: {output_path}")

    def out(text: str) -> None:
        print(text, flush=True)
        output_file.write(text + "\n")
        output_file.flush()

    err("Press Ctrl+C to stop.\n")

    tmpdir = tempfile.mkdtemp(prefix="chrome-translate-")
    chunk_idx = 0
    seen = set()

    try:
        while True:
            chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx:06d}.wav")
            chunk_idx += 1

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "avfoundation",
                "-i", device,
                "-t", str(args.chunk_seconds),
                "-ar", "16000",
                "-ac", "1",
                "-sample_fmt", "s16",
                chunk_path,
            ]
            proc = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if proc.returncode != 0:
                err(f"ffmpeg error: {proc.stderr[-200:]}")
                time.sleep(1)
                continue

            if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < 1000:
                continue

            text, segments = transcribe(chunk_path, api_key, args.source_language, diarize=args.diarize)
            text = text.strip()

            if not text or text in seen:
                try:
                    os.unlink(chunk_path)
                except OSError:
                    pass
                continue

            # Skip common hallucinations/noise
            skip = {"thank you.", "thanks for watching!", "subscribe!", "like and subscribe!", "bye.", "bye!", "you"}
            if text.lower().strip(".") in {s.rstrip(".") for s in skip}:
                seen.add(text)
                try:
                    os.unlink(chunk_path)
                except OSError:
                    pass
                continue

            seen.add(text)

            if args.diarize and segments:
                speaker_parts = detect_speakers(segments)
                if speaker_parts:
                    for speaker, part_text in speaker_parts:
                        if not part_text:
                            continue
                        labeled = f"{speaker}: {part_text}"
                        out(f"\n{labeled}")
                        if not args.no_translate:
                            translated = translate(labeled, args.target_language, api_key, args.openai_model)
                            if translated:
                                out(translated)
                    try:
                        os.unlink(chunk_path)
                    except OSError:
                        pass
                    continue

            out(f"\n[{args.source_language.upper()}] {text}")

            if not args.no_translate:
                translated = translate(text, args.target_language, api_key, args.openai_model)
                if translated:
                    out(f"[{args.target_language}] {translated}")

            try:
                os.unlink(chunk_path)
            except OSError:
                pass

    except KeyboardInterrupt:
        err("\nStopping.")
    finally:
        output_file.close()
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        if original_device_uid:
            switch_output_device_by_uid(original_device_uid)
            err("Restored original output device.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
