# Technical Reference: Video Translation Studio

## Purpose

This application translates and dubs uploaded videos. Users select a source language and target language, then receive:

- a dubbed MP4
- a translated SRT subtitle file

The app now supports persistent settings and Windows packaging for use on stronger machines.

## Runtime Architecture

- FastAPI serves the web UI and API
- background worker threads process jobs
- settings are stored in `%APPDATA%\VideoTranslationStudio\settings.json`
- uploads and outputs are also stored in the app-data directory

## Main Settings

Stored keys:

- `gemini_api_key`
- `hf_token`
- `gemini_transcribe_models`
- `uzbek_tts_mode`
- `sayro_device`

Uzbek TTS modes:

- `mms`
- `auto`
- `sayro`

## Settings API

### `GET /api/settings`

Returns:

- non-secret settings values
- boolean flags showing whether secret keys are already saved
- the app-data settings file path

### `POST /api/settings`

Validates and persists settings. Secret fields are only replaced when a new non-empty value is submitted.

## TTS Routing

English:

- Kokoro

Russian:

- Kokoro

Uzbek:

- `mms` mode -> Meta MMS only
- `auto` mode -> Sayro first, MMS fallback
- `sayro` mode -> Sayro only

## File Locations

Resource directory:

- source run: project root
- packaged run: PyInstaller extraction directory

User data directory:

```text
%APPDATA%\VideoTranslationStudio
```

Runtime subdirectories:

```text
uploads\
outputs\
settings.json
```

## Packaging

Launcher:

- `launcher.py`

Build script:

- `build_windows_app.ps1`

Build dependency list:

- `requirements-build.txt`

The packaged launcher:

- finds an open localhost port
- starts Uvicorn without reload
- opens the default browser automatically

## UI Changes

The main page now includes:

- saved settings panel
- Gemini API key input
- Hugging Face token input
- Gemini model-order input
- Uzbek TTS mode selector
- Sayro device selector
- current Uzbek mode display

## Operational Notes

- On older CPUs, `mms` mode is the recommended Uzbek option.
- `auto` and `sayro` may be very slow on weak hardware.
- The first Sayro segment can take a long time while the model warms up.
- The app emits heartbeat progress updates during long TTS work so the UI does not appear completely dead.
