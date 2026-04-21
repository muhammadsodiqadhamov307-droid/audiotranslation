# Video Translation Studio

Video Translation Studio is a local FastAPI app that uploads a video, transcribes and translates speech with Gemini, generates dubbed audio locally, and returns:

- a dubbed `.mp4`
- a downloadable translated `.srt`
- the subtitle track embedded into the MP4 as `mov_text`

It now behaves more like a real Windows app:

- persistent settings UI for `GEMINI_API_KEY`, `HF_TOKEN`, and model choices
- selectable Uzbek TTS mode
- hidden background launcher
- Windows packaging script for building an `.exe`

## Stack

- Backend: FastAPI + Uvicorn
- Frontend: single-page HTML/CSS/JS
- Transcription + translation: `google-genai` with Gemini Flash models
- English/Russian TTS: Kokoro local CPU TTS
- Uzbek TTS:
  - `mms` mode: Meta MMS only
  - `auto` mode: Sayro first, then MMS fallback
  - `sayro` mode: Sayro only
- Media processing: FFmpeg and FFprobe

## Settings

The app stores persistent settings in:

```text
%APPDATA%\VideoTranslationStudio\settings.json
```

The settings screen in the app lets you save:

- `GEMINI_API_KEY`
- `HF_TOKEN`
- Gemini model order
- Uzbek TTS mode
- Sayro device

Secrets are not echoed back into the UI. The app only reports whether a key or token is already saved.

## Uzbek TTS Modes

- `Fast Uzbek (MMS)`: best choice for older Windows PCs
- `Hybrid Uzbek (Sayro then MMS)`: uses Sayro when possible and falls back automatically
- `Sayro Only`: highest ambition, but slow on weaker hardware

For an older machine, keep Uzbek mode on `mms`.

## Setup

Get a Gemini API key:

```text
https://aistudio.google.com/apikey
```

If you want Sayro, request access at:

```text
https://huggingface.co/uzlm/sayro-tts-1.7B
```

Then create `.env` from `.env.example` if you want file-based defaults, or just enter the keys in the app settings UI.

Install dependencies:

```powershell
pip install -r requirements.txt
```

## FFmpeg

Windows:

```powershell
winget install ffmpeg
```

macOS:

```bash
brew install ffmpeg
```

Linux:

```bash
sudo apt install ffmpeg
```

Verify:

```powershell
ffmpeg -version
ffprobe -version
```

## Run From Source

Standard dev server:

```powershell
uvicorn app:app --reload --port 8000
```

Hidden Windows launcher:

```powershell
.\start_server_hidden.ps1
```

Stop it with:

```powershell
.\stop_server.ps1
```

Open:

```text
http://127.0.0.1:8000
```

## Build A Windows App

Install build dependency:

```powershell
pip install -r requirements-build.txt
```

Then build:

```powershell
.\build_windows_app.ps1
```

This creates:

```text
dist\VideoTranslationStudio\VideoTranslationStudio.exe
```

The packaged app launches a local server and opens the browser automatically.

## Runtime Data

Uploads, outputs, and settings are stored in the user app-data folder, not in the install directory. That makes the packaged app easier to move to another Windows PC.

## Notes

- Sayro is large and slow on older CPUs.
- MMS is the practical default on weak hardware.
- The first Sayro run on a stronger PC may still take time while the model warms up.
- The MMS Uzbek model expects Cyrillic, so the app converts Uzbek Latin text before synthesis.
