# Gemini Video Translation And Dubbing

A local FastAPI web app that uploads a video, translates its speech with the Gemini API, generates dubbed audio with Gemini TTS, and returns:

- A dubbed `.mp4`
- A downloadable translated `.srt`
- The `.srt` embedded in the MP4 as a soft subtitle track

Everything is processed locally except the Gemini API calls. There is no Google Cloud Speech-to-Text, no Cloud Translation, no Cloud Text-to-Speech, and no Cloud Storage.

## Project Structure

```text
project/
├── app.py
├── pipeline/
│   ├── extract_audio.py
│   ├── chunk_audio.py
│   ├── transcribe_translate.py
│   ├── text_to_speech.py
│   ├── subtitles.py
│   └── merge_video.py
├── static/
│   ├── index.html
│   └── style.css
├── uploads/
├── outputs/
├── requirements.txt
├── .env.example
└── README.md
```

## Gemini API Key

Get your key from:

```text
https://aistudio.google.com/apikey
```

Copy `.env.example` to `.env` and set:

```env
GEMINI_API_KEY=your_key_here
```

This project uses the new `google-genai` SDK, not the older `google-generativeai` SDK.

## Models Used

- `gemini-2.5-flash`: transcribes each audio chunk and translates each segment in one JSON response. The app can fall back to other Flash models if a request receives `429 RESOURCE_EXHAUSTED`.
- `gemini-3.1-flash-tts-preview`: generates PCM speech audio from translated text. This is the default because it has separate TTS quota from the older 2.5 Flash TTS model.

You can optionally override them:

```env
GEMINI_TRANSCRIBE_MODELS=gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-3.1-flash-lite-preview
GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
GEMINI_TTS_REQUEST_INTERVAL_SECONDS=7.0
GEMINI_TTS_MAX_RETRIES=6
```

Gemini TTS currently supports a fixed set of spoken languages. Russian and English are supported. Uzbek may not be supported by the TTS model; if Uzbek TTS fails, the app retries with a neutral English voice and shows a warning in the UI.

The default TTS request interval keeps requests under a 10 RPM model quota. Lowering it can make jobs faster, but it increases the chance of `429 RESOURCE_EXHAUSTED`.

## Install FFmpeg

FFmpeg and FFprobe must be installed and available in `PATH`.

### Windows

```powershell
winget install ffmpeg
```

Restart PowerShell and verify:

```powershell
ffmpeg -version
ffprobe -version
```

### macOS

```bash
brew install ffmpeg
ffmpeg -version
ffprobe -version
```

### Linux

```bash
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
ffprobe -version
```

## Run Locally

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app:app --reload --port 8000
```

macOS or Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

## Pipeline

1. The browser uploads the video in 8 MB chunks.
2. FFmpeg extracts the audio as MP3:

```bash
ffmpeg -i input_video -q:a 0 -map a full_audio.mp3
```

3. FFmpeg splits the MP3 into local chunks. Each chunk starts at `chunk_index * 55` seconds and includes about 2 seconds of overlap.
4. Each chunk is uploaded with the Gemini Files API:

```python
myfile = client.files.upload(file="chunk_000.mp3")
```

5. `gemini-2.0-flash` receives the uploaded audio file and returns only JSON:

```json
[
  {
    "start_sec": 1.0,
    "end_sec": 4.5,
    "text": "Original speech",
    "translated_text": "Translated speech"
  }
]
```

6. The app offsets each chunk timestamp by `chunk_index * 55`.
7. The app drops segments from later chunks that begin in the leading 2-second overlap zone.
8. Gemini TTS generates PCM audio for each translated segment.
9. The app saves Gemini PCM output as WAV with proper headers.
10. FFmpeg applies chained `atempo` filters so each generated segment fits the original timing.
11. FFmpeg concatenates all timed segments into `dubbed_audio.wav`.
12. The app writes a valid `.srt`.
13. FFmpeg merges the original video stream, dubbed audio, and subtitles:

```bash
ffmpeg -i original_video -i dubbed_audio.wav -i subtitles.srt \
  -map 0:v -map 1:a -map 2 \
  -c:v copy -c:a aac -c:s mov_text \
  -metadata:s:s:0 language=<target_lang_code> \
  output.mp4
```

## Error Handling

- Source and target languages cannot be the same.
- If Gemini returns invalid JSON for a chunk, the app retries once with a stricter prompt.
- If the retry fails, the chunk is skipped and a warning is shown.
- If Gemini TTS fails for Uzbek, the app retries with a neutral English voice and shows a warning.
- Temporary chunks and segment WAV files are removed after completion or failure.
- Output files are deleted after download.

## Notes

Gemini audio understanding can produce useful timestamps, but it is not a dedicated forced-alignment engine. For professional lip-sync or exact subtitle timing, a speech alignment model would be more precise. This implementation follows the requested Gemini-only constraint.
