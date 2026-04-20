# Gemini + Kokoro Video Translation And Dubbing

A local FastAPI web app that uploads a video, transcribes and translates speech with Gemini, generates dubbed speech locally with Kokoro TTS, and returns:

- A dubbed `.mp4`
- A downloadable translated `.srt`
- The `.srt` embedded in the MP4 as a soft subtitle track

Everything is local except the Gemini transcription/translation calls. There is no Google Cloud, no Cloud Storage, and no Gemini TTS quota.

## Stack

- Backend: FastAPI + Uvicorn
- Frontend: single-page HTML/CSS/JS
- Transcription + translation: `google-genai` with Gemini Flash models
- TTS: Kokoro local CPU TTS
- Media processing: FFmpeg and FFprobe
- Credentials: `GEMINI_API_KEY` in `.env`

## Project Structure

```text
project/
|-- app.py
|-- pipeline/
|   |-- extract_audio.py
|   |-- chunk_audio.py
|   |-- transcribe_translate.py
|   |-- text_to_speech.py
|   |-- subtitles.py
|   `-- merge_video.py
|-- static/
|   |-- index.html
|   `-- style.css
|-- uploads/
|-- outputs/
|-- requirements.txt
|-- .env.example
`-- README.md
```

## Setup

Get a Gemini API key:

```text
https://aistudio.google.com/apikey
```

Copy `.env.example` to `.env` and set:

```env
GEMINI_API_KEY=your_key_here
```

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

## Run

```powershell
uvicorn app:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

## Models And Voices

Gemini transcription/translation fallback chain:

```env
GEMINI_TRANSCRIBE_MODELS=gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-3.1-flash-lite-preview
```

Kokoro default voice configuration:

```env
KOKORO_EN_LANG=a
KOKORO_EN_VOICE=af_heart
KOKORO_RU_LANG=r
KOKORO_RU_VOICE=rf_voice
KOKORO_UZ_LANG=r
KOKORO_UZ_VOICE=rf_voice
```

Kokoro voice reference:

```text
https://huggingface.co/hexgrad/Kokoro-82M
```

Note: the installed `kokoro` package version may not include Russian `r` language support. The app tries the configured language/voice first. If Kokoro rejects it, the app falls back to `a` / `af_heart` and shows a warning instead of failing the job.

## Pipeline

1. Browser uploads the video in 8 MB chunks.
2. FFmpeg extracts audio:

```bash
ffmpeg -i input_video -q:a 0 -map a full_audio.mp3
```

3. FFmpeg creates overlapping 55-second MP3 chunks.
4. Each chunk is uploaded with Gemini Files API:

```python
myfile = client.files.upload(file="chunk_000.mp3")
```

5. Gemini returns JSON:

```json
[
  {
    "start_sec": 0.5,
    "end_sec": 2.0,
    "original_text": "Original speech",
    "translated_text": "Translated speech"
  }
]
```

6. The app offsets chunk timestamps by `chunk_index * 55`.
7. The app deduplicates overlap using the previous chunk's last end time minus 2 seconds.
8. Kokoro generates local WAV audio for each translated segment at 24000 Hz.
9. FFmpeg applies chained `atempo` filters to match segment timing.
10. FFmpeg concatenates timed WAV files into `dubbed_audio.wav`.
11. The app writes `translated_subtitles.srt`.
12. FFmpeg merges original video, dubbed audio, and subtitles:

```bash
ffmpeg -i original_video \
       -i dubbed_audio.wav \
       -i subtitles.srt \
       -map 0:v \
       -map 1:a \
       -map 2 \
       -c:v copy \
       -c:a aac \
       -c:s mov_text \
       -metadata:s:s:0 language=<target_lang_code> \
       output.mp4
```

## Error Handling

- Source and target languages cannot be the same.
- Invalid Gemini JSON is retried once with a stricter prompt.
- Failed Gemini chunks are skipped with warnings.
- If Kokoro fails for a segment, the app inserts silence of the same duration and continues.
- Extreme `atempo` ratios are clamped and surfaced as warnings.
- Uploads and intermediate files are deleted after completion or failure.

