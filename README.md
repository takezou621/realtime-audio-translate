# whisper.cpp realtime translation CLI

Local microphone input is transcribed and translated with `whisper.cpp`.

## Setup

### whisper.cpp (local mic / Teams)

```bash
./whisper-translate setup base
```

On the first run this downloads `models/ggml-base.bin` inside `vendor/whisper.cpp`
and builds `build/bin/whisper-stream` with SDL2 microphone support.

### Chrome audio capture (YouTube, Teams, etc.)

No whisper.cpp build needed. Requires:

- [BlackHole 2ch](https://existential.audio/blackhole/) (`brew install blackhole-2ch`)
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg`)
- OpenAI API key in `.env`:

```bash
cp .env.example .env
# Edit .env and set your OpenAI API key
```

`.env` format:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get your API key from https://platform.openai.com/api-keys

macOS audio routing (set up once):

1. Open **Audio MIDI Setup**.
2. Create a **Multi-Output Device** that includes your normal speaker/headphones
   and **BlackHole 2ch**.
3. Set macOS sound output to that Multi-Output Device.

This routes all system audio (Chrome, YouTube, Teams web, etc.) through
BlackHole, which the script captures.

## Chrome audio translation

```bash
./whisper-translate chrome
```

Captures Chrome's audio output via BlackHole, transcribes with the OpenAI
Whisper API, and translates to Japanese.

```
Capturing from device: :1
Chunk size: 5s | Source: en | Target: Japanese
Press Ctrl+C to stop.

[EN] I'm McDonald's. I'm going to teach you some phrases to use when you order
[Japanese] 私はマクドナルドです。注文するときに使えるフレーズを教えます。

[EN] I'd like to order a Big Mac.
[Japanese] ビッグマックを注文したいです。
```

### Options

```bash
./whisper-translate chrome --source-language ja      # Japanese speech → Japanese transcript
./whisper-translate chrome --target-language English   # Translate into English
./whisper-translate chrome --no-translate              # Transcript only, no translation
./whisper-translate chrome --chunk-seconds 3           # Shorter chunks for lower latency
./whisper-translate chrome --openai-model gpt-4o       # Use a different translation model
./whisper-translate chrome --device ":1"               # Force specific ffmpeg device
```

| Option | Default | Description |
|---|---|---|
| `--source-language` | `en` | Language code for Whisper transcription |
| `--target-language` | `Japanese` | Translation target language |
| `--openai-model` | `gpt-4o-mini` | OpenAI model for translation |
| `--chunk-seconds` | `5` | Audio capture duration per chunk |
| `--no-translate` | off | Show transcript only, skip translation |
| `--device` | auto | ffmpeg AVFoundation device (`:N`), auto-detects BlackHole |

## Run Japanese to English translation (local mic)

```bash
./whisper-translate run --model base --language ja
```

Useful options:

```bash
./whisper-translate run --model small --language ja --length 7000
./whisper-translate run --model tiny --language ja --step 300 --length 3000
./whisper-translate run --model base --language ja --capture 1 --output translation.txt
```

`--translate` in Whisper translates the source speech to English. For Japanese
input, `--language ja` keeps language detection stable.

## Teams English to Japanese

Whisper's built-in `--translate` only translates into English. For Teams calls
where participants speak English and you want Japanese, use the Teams command:

```bash
export OPENAI_API_KEY="..."
./whisper-translate teams --model base
```

This opens Microsoft Teams in Google Chrome, looks for the BlackHole capture
device, transcribes English meeting audio with `whisper.cpp`, and translates the
transcript to Japanese with the OpenAI Responses API.

If BlackHole is not selected automatically, pass the capture ID shown at startup:

```bash
./whisper-translate teams --model base --capture 3
```

Useful Teams options:

```bash
./whisper-translate teams --model small --capture-name BlackHole
./whisper-translate teams --model base --no-translate
./whisper-translate teams --model base --transcript-file teams-en.txt
```

For a specific Teams meeting URL:

```bash
./whisper-translate teams --model base --teams-url 'https://teams.live.com/meet/9353409285266?p=W4Dw7PcXmb54nyx243'
```

## Test With Generated Audio

```bash
./scripts/test_audio_translate.sh
```

This creates `test_audio/teams_test.wav`, transcribes it with `whisper.cpp`, and
writes:

- `test_audio/teams_test.en.txt`
- `test_audio/teams_test.ja.txt`

If `OPENAI_API_KEY` is set, the Japanese file is produced through the same
OpenAI translation path used for Teams. Without an API key, the script uses a
deterministic fixture translation so the local audio and transcription pipeline
can still be checked.

## Commands

```bash
./whisper-translate help
./whisper-translate chrome --help
./whisper-translate run --help
./whisper-translate teams --help
```

`run` supports:

- `--model`: `tiny`, `base`, `small`, `medium`, etc.
- `--language`: source speech language, for example `ja`, `en`, `zh`, `ko`.
- `--capture`: microphone device ID. The default `-1` uses the system default.
- `--output`: write text output to a file as well as the terminal.
- `--keep-context`: keep prior text as context between chunks.
- `--no-gpu`: force CPU inference.

## Notes

- Smaller models are faster but less accurate: `tiny` < `base` < `small` < `medium`.
- If macOS asks for microphone permission, allow Terminal or the app running this script.
- Current `whisper.cpp` revision used here:

```bash
git -C vendor/whisper.cpp log -1 --format='%h %cd %s' --date=short
```
