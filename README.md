# Realtime Audio Translate

[English](#english) | [日本語](#日本語)

---

<a id="english"></a>

## English

Real-time CLI tool that captures system audio (Chrome, YouTube, Teams, etc.) and translates speech using Whisper + OpenAI.

### Setup

#### Chrome audio capture (YouTube, Teams, etc.)

Requires:

- [BlackHole 2ch](https://existential.audio/blackhole/) (`brew install blackhole-2ch`)
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg`)
- OpenAI API key:

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
2. Create a **Multi-Output Device** that includes your normal speaker/headphones and **BlackHole 2ch**.
3. Set macOS sound output to that Multi-Output Device.

This routes all system audio through BlackHole, which the script captures.

#### whisper.cpp (local mic / Teams)

```bash
./whisper-translate setup base
```

Downloads `models/ggml-base.bin` and builds `build/bin/whisper-stream` with SDL2 microphone support.

### Usage

#### Chrome audio translation

```bash
./whisper-translate chrome
```

Captures Chrome's audio output via BlackHole, transcribes with the OpenAI Whisper API, and translates to Japanese.

```
Capturing from device: :1
Chunk size: 5s | Source: en | Target: Japanese
Press Ctrl+C to stop.

[EN] I'm going to teach you some phrases to use when you order
[Japanese] 注文するときに使えるフレーズを教えます。

[EN] I'd like to order a Big Mac.
[Japanese] ビッグマックを注文したいです。
```

#### Speaker diarization

Add `--diarize` to identify speakers (話者A, 話者B) in the output:

```bash
# Chrome mode (uses Whisper API verbose_json to detect speaker turns)
./whisper-translate chrome --diarize

# Teams / local mic mode (requires a -tdrz model)
./whisper-translate setup base-tdrz
./whisper-translate teams --model base --diarize
./whisper-translate run --model base --diarize
```

Output with diarization:

```
話者A: Hello, how are you?
話者A: こんにちは、お元気ですか？
話者B: I'm doing great.
話者B: 元気です、ありがとう。
```

#### Local microphone translation

```bash
./whisper-translate run --model base --language ja
```

#### Teams meeting translation

```bash
export OPENAI_API_KEY="..."
./whisper-translate teams --model base
```

### Chrome command options

```bash
./whisper-translate chrome --source-language ja      # Japanese speech input
./whisper-translate chrome --target-language English  # Translate into English
./whisper-translate chrome --no-translate             # Transcript only
./whisper-translate chrome --chunk-seconds 3          # Shorter chunks for lower latency
./whisper-translate chrome --openai-model gpt-4o      # Use a different model
./whisper-translate chrome --device ":1"              # Force specific ffmpeg device
```

| Option | Default | Description |
|---|---|---|
| `--source-language` | `en` | Language code for Whisper transcription |
| `--target-language` | `Japanese` | Translation target language |
| `--openai-model` | `gpt-4o-mini` | OpenAI model for translation |
| `--chunk-seconds` | `5` | Audio capture duration per chunk |
| `--no-translate` | off | Show transcript only, skip translation |
| `--device` | auto | ffmpeg AVFoundation device (`:N`), auto-detects BlackHole |

### Commands

```bash
./whisper-translate help
./whisper-translate chrome --help
./whisper-translate run --help
./whisper-translate teams --help
```

### Notes

- Smaller models are faster but less accurate: `tiny` < `base` < `small` < `medium`.
- If macOS asks for microphone permission, allow Terminal or the app running this script.

---

<a id="日本語"></a>

## 日本語

Chrome（YouTube、Teamsなど）のシステム音声をキャプチャし、Whisper + OpenAIでリアルタイム翻訳するCLIツールです。

### セットアップ

#### Chrome音声キャプチャ（YouTube、Teamsなど）

必要なもの:

- [BlackHole 2ch](https://existential.audio/blackhole/) (`brew install blackhole-2ch`)
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg`)
- OpenAI APIキー:

```bash
cp .env.example .env
# .envを編集してOpenAI APIキーを設定
```

`.env` の書式:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

APIキーの取得: https://platform.openai.com/api-keys

macOS音声ルーティングの設定（初回のみ）:

1. **Audio MIDI Setup**（オーディオ MIDI セットアップ）を開く。
2. 通常使用しているスピーカー/ヘッドホンと **BlackHole 2ch** を含む **複数出力装置**（Multi-Output Device）を作成。
3. macOSのサウンド出力をその複数出力装置に設定。

これによりシステム音声がBlackHoleを経由し、スクリプトでキャプチャできるようになります。

#### whisper.cpp（ローカルマイク / Teams）

```bash
./whisper-translate setup base
```

`models/ggml-base.bin` をダウンロードし、SDL2マイク対応の `build/bin/whisper-stream` をビルドします。

### 使い方

#### Chrome音声のリアルタイム翻訳

```bash
./whisper-translate chrome
```

BlackHole経由でChromeの音声出力をキャプチャし、OpenAI Whisper APIで文字起こし、日本語に翻訳します。

```
Capturing from device: :1
Chunk size: 5s | Source: en | Target: Japanese
Press Ctrl+C to stop.

[EN] I'm going to teach you some phrases to use when you order
[Japanese] 注文するときに使えるフレーズを教えます。

[EN] I'd like to order a Big Mac.
[Japanese] ビッグマックを注文したいです。
```

#### 話者識別（Diarization）

`--diarize` を追加すると、話者（話者A、話者B）を識別して出力します:

```bash
# Chromeモード（Whisper APIのverbose_jsonで話者ターンを検出）
./whisper-translate chrome --diarize

# Teams / ローカルマイクモード（-tdrzモデルが必要）
./whisper-translate setup base-tdrz
./whisper-translate teams --model base --diarize
./whisper-translate run --model base --diarize
```

話者識別ありの出力:

```
話者A: Hello, how are you?
話者A: こんにちは、お元気ですか？
話者B: I'm doing great.
話者B: 元気です、ありがとう。
```

#### ローカルマイク翻訳

```bash
./whisper-translate run --model base --language ja
```

#### Teams会議翻訳

```bash
export OPENAI_API_KEY="..."
./whisper-translate teams --model base
```

### chromeコマンドのオプション

```bash
./whisper-translate chrome --source-language ja      # 日本語音声を入力
./whisper-translate chrome --target-language English  # 英語に翻訳
./whisper-translate chrome --no-translate             # 文字起こしのみ
./whisper-translate chrome --chunk-seconds 3          # チャンクを短くして低遅延化
./whisper-translate chrome --openai-model gpt-4o      # 翻訳モデルを変更
./whisper-translate chrome --device ":1"              # ffmpegデバイスを明示指定
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--source-language` | `en` | Whisper文字起こしの言語コード |
| `--target-language` | `Japanese` | 翻訳先の言語 |
| `--openai-model` | `gpt-4o-mini` | 翻訳に使用するOpenAIモデル |
| `--chunk-seconds` | `5` | 1チャンクあたりの音声キャプチャ秒数 |
| `--no-translate` | off | 文字起こしのみ、翻訳をスキップ |
| `--device` | 自動 | ffmpeg AVFoundationデバイス（`:N`）、自動検出はBlackHole |

### コマンド一覧

```bash
./whisper-translate help
./whisper-translate chrome --help
./whisper-translate run --help
./whisper-translate teams --help
```

### 補足

- モデルが小さいほど高速ですが精度は下がります: `tiny` < `base` < `small` < `medium`
- macOSがマイクの許可を求めた場合は、ターミナルまたは実行アプリを許可してください。
