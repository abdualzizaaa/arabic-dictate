# 🎙️ arabic-dictate — Arabic dictation & meeting transcription

Fully **local-first Arabic speech-to-text**: speak, and the Arabic text is typed right at your
cursor in the active window — directly inside the terminal. Your text is never submitted
automatically; you review it and press Enter yourself.

With **meeting transcription**: turn long meeting recordings into a structured, speaker-labeled
transcript — Speaker 1, Speaker 2, Speaker 3…

**العربية:** [README.md](README.md) · **Full guide (Arabic):** [GUIDE.ar.md](GUIDE.ar.md)

![License MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Platform Linux (X11)](https://img.shields.io/badge/Platform-Linux%20(X11)-lightgrey.svg)
![Local-first](https://img.shields.io/badge/Local--first-100%25-success.svg)

---

## ✨ Features

- 🎙 **Instant dictation** — system-tray icon + `Ctrl+Alt+D`; the text is pasted at your cursor in any window.
- 🧠 **Three Arabic engines** — Cohere Arabic model locally (most accurate, ~4.7× realtime), Whisper
  locally (offline after first download), or the Cohere cloud API (fastest, free key).
- 🛡 **Hallucination guard** — a WebRTC-VAD silence gate, a dynamic energy gate, and a known-phrase
  filter stop noise from being pasted as fake text.
- 👥 **Meeting transcription** — records microphone + system audio, then produces a diarized
  transcript (Speaker 1/2/3) as `txt` / `srt` / `json` with talk-time stats.
- 🔒 **Private** — everything runs on your machine; audio never leaves it unless you explicitly
  pick the cloud engine.

## 🚀 Quick start (Ubuntu / Debian)

```bash
git clone https://github.com/abdualzizaaa/arabic-dictate.git
cd arabic-dictate
./install.sh              # Python env + global command (fast install)
arabic-dictate doctor     # verify environment and engines
```

Then click the microphone tray icon (or press `Ctrl+Alt+D`), speak, and click again —
the text appears at your cursor. For the most accurate Arabic engine (~3 GB, one time):

```bash
arabic-dictate pull                     # Cohere Arabic int8 model (local)
arabic-dictate engine cohere-local      # make it active
```

> **Terminals** paste with `Ctrl+Shift+V`; this is configured by default. Change `paste_key`
> in the settings if needed.

## 📦 System requirements

```bash
sudo apt install -y python3-venv python3-gi alsa-utils xdotool xclip libnotify-bin \
  gir1.2-ayatanaappindicator3-0.1 ffmpeg
```

| Need | Why |
| --- | --- |
| `alsa-utils` | Microphone capture (`arecord`) |
| `xdotool` + `xclip` | Pasting into the active window (X11) |
| `libnotify-bin` | Desktop notifications (`notify-send`) |
| `python3-gi` + `gir1.2-ayatanaappindicator3-0.1` | System-tray icon |
| `ffmpeg` | Meeting recording and audio-format conversion (optional) |

- GNOME users: enable the AppIndicators extension to see the tray icon
  (`gnome-extensions enable ubuntu-appindicators@ubuntu.com`).
- **X11 is fully supported.** On Wayland, transcription works but pasting and the global
  hotkey are unreliable — see the roadmap.

## 🎙️ Engines — which one?

| Engine | Arabic accuracy | Speed (CPU, no GPU) | Memory | Needs |
| --- | --- | --- | --- | --- |
| `cohere-local` **(default)** | **best** (WER ≈ 25.9)* | **~4.7× realtime** | ~4 GB | model downloaded (`pull`, ≈3 GB once) |
| `whisper-local` | good (WER ≈ 36.9)* | ~1.0× realtime | ~2 GB | nothing (auto-downloads) |
| `cohere-cloud` | **best** (same model) | seconds (network) | none | free Cohere key (`set-key`) |

\* WER figures from the open Arabic ASR leaderboard — your mileage varies by dialect and domain.

```bash
arabic-dictate engine                    # show engines
arabic-dictate engine whisper-local      # switch engine
arabic-dictate pull                      # download the local Cohere model
arabic-dictate set-key <COHERE_API_KEY>  # key for the cloud engine
```

## 👥 Meeting transcription

Record the meeting (microphone + system audio together), then transcribe with speaker labels:

```bash
arabic-dictate meeting setup                             # diarization models (~45 MB, once)
arabic-dictate meeting record --out meeting.wav          # records mic + system audio — Ctrl+C to stop
arabic-dictate meeting transcribe meeting.wav --format srt --out ./transcripts
```

Sample output:

```text
[00:00:12] Speaker 1:
Welcome everyone, let's review last week's action items.

[00:00:19] Speaker 2:
The performance report is done; the budget review remains.
```

- **Post-meeting diarization** is the practical CPU path (a one-hour meeting takes minutes;
  live streaming diarization needs a GPU).
- Stack: **sherpa-onnx** (clean licenses) — no HuggingFace account, no gated terms.
- Know the speaker count? `--speakers 3`. Leave `0` for automatic detection.
- Output: `txt`, `srt` (subtitles) or `json` (for your tools).

## ⌨️ Common commands

| Command | Purpose |
| --- | --- |
| `arabic-dictate ensure` | start the daemon if it is not running |
| `arabic-dictate start` / `stop` / `toggle` | recording control |
| `arabic-dictate status` | full state (JSON) |
| `arabic-dictate last` / `copy` | last transcript / copy it |
| `arabic-dictate transcribe FILE` | transcribe an audio file |
| `arabic-dictate meeting …` | meeting workflows: `setup` / `record` / `transcribe` |
| `arabic-dictate warmup` / `unload` | preload the model / free memory |
| `arabic-dictate doctor` | full environment check |

The full list lives in [GUIDE.ar.md](GUIDE.ar.md) (Arabic).

## ⚙️ Configuration

File: `~/.config/arabic-dictate/config.json` — after editing: `arabic-dictate reload`.
Key settings: `engine`, `hotkey`, `paste_key`, `inject_mode`, `vad_min_secs`, `vad_threshold`,
and the `meeting` group (speaker count, label template, output dir).

## 🔒 Privacy

- Both local engines run **offline** after first download; your audio never leaves the machine.
- `cohere-cloud` is opt-in: it uploads the audio clip to Cohere for speed — used only when you
  choose it and provide a key.
- The `cohere-local` model is downloaded from HuggingFace with pinned SHA-256 verification.

## 🧩 Optional integrations

- **Command Code**: a session-start hook keeps the daemon running — see
  [integrations/commandcode](integrations/commandcode/README.md).

## 🗺️ Roadmap

- Wayland support (paste + global hotkey).
- Live streaming captions during meetings.
- Named speakers via voice enrollment.
- Optional high-accuracy diarization tier (pyannote community-1).
- OpenVINO / Intel-GPU acceleration.
- PyPI publishing.

## 🤝 Contributing

Contributions are welcome — start with [CONTRIBUTING.md](CONTRIBUTING.md). This project follows
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## 📄 License & credits

MIT — see [LICENSE](LICENSE). Standing on the shoulders of:

- [Cohere Transcribe Arabic](https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026)
  (Apache-2.0) — via a community int8 CPU derivative.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + CTranslate2 — Whisper engine.
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (Apache-2.0) + pyannote segmentation-3.0
  (MIT) + 3D-Speaker CAM++ (Apache-2.0) — speaker diarization.
- WebRTC VAD — silence gate.
