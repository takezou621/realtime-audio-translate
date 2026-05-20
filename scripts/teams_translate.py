#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WHISPER_DIR = ROOT_DIR / "vendor" / "whisper.cpp"
WHISPER_BIN = WHISPER_DIR / "build" / "bin" / "whisper-stream"
TEAMS_URL = "https://teams.microsoft.com/v2/"


def load_env_file(path: Path = ROOT_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run_open_chrome(url: str) -> None:
    try:
        subprocess.run(["open", "-a", "Google Chrome", url], check=False)
    except FileNotFoundError:
        subprocess.run(["open", url], check=False)


def model_path(model: str) -> Path:
    return WHISPER_DIR / "models" / f"ggml-{model}.bin"


def ensure_ready(model: str, diarize: bool = False) -> None:
    effective = f"{model}-tdrz" if diarize else model
    if not WHISPER_BIN.exists():
        raise SystemExit(
            "whisper-stream is missing. Run: ./whisper-translate setup " + model
        )
    if not model_path(effective).exists():
        raise SystemExit(
            f"Model '{effective}' is missing. Run: ./whisper-translate setup {effective}"
        )


def parse_capture_devices(lines: list[str]) -> dict[int, str]:
    devices: dict[int, str] = {}
    pattern = re.compile(r"Capture device #(\d+): '(.+)'")
    for line in lines:
        match = pattern.search(line)
        if match:
            devices[int(match.group(1))] = match.group(2)
    return devices


def list_capture_devices(model: str, language: str, timeout: float = 4.0) -> dict[int, str]:
    cmd = [
        str(WHISPER_BIN),
        "-m",
        str(model_path(model)),
        "--capture",
        "-1",
        "--language",
        language,
        "--step",
        "500",
        "--length",
        "1000",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    start = time.monotonic()
    try:
        assert proc.stdout is not None
        while time.monotonic() - start < timeout:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            lines.append(line.rstrip())
            if "attempt to open default capture device" in line:
                break
    finally:
        stop_process(proc)
    return parse_capture_devices(lines)


def choose_capture_id(args: argparse.Namespace) -> int:
    if args.capture != "auto":
        return int(args.capture)

    devices = list_capture_devices(args.model, args.source_language)
    if not devices:
        eprint("No capture devices were listed by whisper-stream; using system default.")
        return -1

    eprint("Capture devices:")
    for device_id, name in devices.items():
        eprint(f"  {device_id}: {name}")

    wanted = args.capture_name.casefold()
    for device_id, name in devices.items():
        if wanted in name.casefold():
            eprint(f"Using capture device #{device_id}: {name}")
            return device_id

    eprint(f"Capture device matching '{args.capture_name}' was not found; using default.")
    return -1


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def translate_openai(text: str, target_language: str, model: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    has_speaker = any(text.startswith(f"{s}:") or text.startswith(f"{s}：") for s in SPEAKER_LABELS)
    if has_speaker:
        instructions = (
            f"Translate meeting speech into natural {target_language}. "
            "Preserve the speaker label (話者A/話者B) at the start of the line. "
            "Return only the translation. Preserve names, product names, numbers, "
            "dates, action items, and technical terms."
        )
    else:
        instructions = (
            f"Translate meeting speech into natural {target_language}. "
            "Return only the translation. Preserve names, product names, numbers, "
            "dates, action items, and technical terms."
        )

    body = {
        "model": model,
        "instructions": instructions,
        "input": text,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail}") from exc

    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()

    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks).strip()


def read_new_text(path: Path, offset: int) -> tuple[int, list[str]]:
    if not path.exists():
        return offset, []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        data = handle.read()
        offset = handle.tell()
    lines = [line.strip() for line in data.splitlines() if line.strip()]
    return offset, lines


def normalize_transcript_line(line: str, preserve_speaker_turns: bool = False) -> str:
    line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
    if preserve_speaker_turns:
        line = re.sub(r"^\[(?!SPEAKER_TURN\])[^\]]+\]\s*", "", line).strip()
    else:
        line = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
    line = re.sub(r"\s+", " ", line)
    return line


def should_skip_transcript(text: str) -> bool:
    if not text:
        return True
    marker = text.strip().upper()
    return marker in {
        "[BLANK_AUDIO]",
        "BLANK_AUDIO",
        "[MUSIC]",
        "MUSIC",
        "[NO SPEECH]",
        "NO SPEECH",
    }


SPEAKER_LABELS = ["話者A", "話者B"]


def parse_speaker_turns(text: str) -> list[tuple[str, str]]:
    """Split text on [SPEAKER_TURN] markers and return (speaker, text) pairs."""
    parts = re.split(r"\[SPEAKER_TURN\]\s*", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []
    return [(SPEAKER_LABELS[i % len(SPEAKER_LABELS)], part) for i, part in enumerate(parts)]


def start_log_thread(proc: subprocess.Popen[str]) -> threading.Thread:
    def relay() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.strip():
                eprint(line.rstrip())

    thread = threading.Thread(target=relay, daemon=True)
    thread.start()
    return thread


def run(args: argparse.Namespace) -> int:
    ensure_ready(args.model, args.diarize)

    if args.open_teams:
        run_open_chrome(args.teams_url)
        eprint("Opened Microsoft Teams in Google Chrome.")
        eprint("Log in and join the meeting in Chrome if it is not already open.")

    capture_id = choose_capture_id(args)

    transcript_file = Path(args.transcript_file) if args.transcript_file else Path(
        tempfile.NamedTemporaryFile(prefix="teams-whisper-", suffix=".txt", delete=True).name
    )
    transcript_file.parent.mkdir(parents=True, exist_ok=True)
    transcript_file.write_text("", encoding="utf-8")

    effective_model = f"{args.model}-tdrz" if args.diarize else args.model
    cmd = [
        str(WHISPER_BIN),
        "-m",
        str(model_path(effective_model)),
        "-t",
        str(args.threads),
        "--step",
        str(args.step),
        "--length",
        str(args.length),
        "--keep",
        str(args.keep),
        "--capture",
        str(capture_id),
        "--language",
        args.source_language,
        "--file",
        str(transcript_file),
    ]
    if args.diarize:
        cmd.append("--tinydiarize")
    if args.keep_context:
        cmd.append("--keep-context")
    if args.no_gpu:
        cmd.append("--no-gpu")

    eprint("Starting English transcription from Teams/Chrome audio.")
    if args.diarize:
        eprint("Speaker diarization enabled (model: %s)." % effective_model)
    eprint(f"Transcript file: {transcript_file}")
    eprint("Press Ctrl+C to stop.")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    start_log_thread(proc)

    seen: set[str] = set()
    offset = 0
    try:
        while proc.poll() is None:
            offset, lines = read_new_text(transcript_file, offset)
            for raw_line in lines:
                text = normalize_transcript_line(raw_line, preserve_speaker_turns=args.diarize)
                content_for_dedup = re.sub(r"\[SPEAKER_TURN\]\s*", "", text).strip()
                if should_skip_transcript(content_for_dedup) or content_for_dedup in seen:
                    continue
                seen.add(content_for_dedup)

                if args.diarize and "[SPEAKER_TURN]" in text:
                    for speaker, part_text in parse_speaker_turns(text):
                        labeled = f"{speaker}: {part_text}"
                        print(f"\n{labeled}", flush=True)
                        if args.no_translate:
                            continue
                        try:
                            translated = translate_openai(labeled, args.target_language, args.openai_model)
                        except Exception as exc:
                            eprint(f"Translation failed: {exc}")
                            continue
                        print(translated, flush=True)
                else:
                    print(f"\nEN: {text}", flush=True)
                    if args.no_translate:
                        continue
                    try:
                        translated = translate_openai(text, args.target_language, args.openai_model)
                    except Exception as exc:
                        eprint(f"Translation failed: {exc}")
                        continue
                    print(f"JA: {translated}", flush=True)
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        eprint("Stopping...")
    finally:
        stop_process(proc)
    return proc.returncode or 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open Teams in Chrome, capture Teams audio, transcribe English, and translate to Japanese."
    )
    parser.add_argument("--model", default="base", help="whisper.cpp model name")
    parser.add_argument("--source-language", default="en", help="speech language")
    parser.add_argument("--target-language", default="Japanese", help="translation target")
    parser.add_argument("--openai-model", default="gpt-4o-mini", help="OpenAI text model")
    parser.add_argument("--capture", default="auto", help="capture device ID, or auto")
    parser.add_argument("--capture-name", default="BlackHole", help="device name to prefer with --capture auto")
    parser.add_argument("--threads", default=str(os.cpu_count() or 4))
    parser.add_argument("--step", default="1000", help="capture step in ms")
    parser.add_argument("--length", default="5000", help="audio window length in ms")
    parser.add_argument("--keep", default="500", help="audio kept from prior chunk in ms")
    parser.add_argument("--keep-context", action="store_true")
    parser.add_argument("--no-gpu", action="store_true")
    parser.add_argument("--diarize", action="store_true", help="enable speaker diarization (requires -tdrz model)")
    parser.add_argument("--no-translate", action="store_true", help="print English transcript only")
    parser.add_argument("--transcript-file", help="where whisper-stream writes English transcript")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--open-teams", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--teams-url", default=TEAMS_URL)
    return parser


if __name__ == "__main__":
    load_env_file()
    raise SystemExit(run(build_parser().parse_args()))
