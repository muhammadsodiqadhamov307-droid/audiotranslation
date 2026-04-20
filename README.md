# Gemini, Kokoro, Sayro Video Translation And Dubbing

A local FastAPI web app that uploads a video, transcribes and translates speech with Gemini, generates dubbed speech locally, and returns:

- A dubbed `.mp4`
- A downloadable translated `.srt`
- The `.srt` embedded in the MP4 as a soft subtitle track

Everything is local except the Gemini transcription and translation calls. There is no Google Cloud project, no Cloud Storage, and no Gemini TTS quota.

## Stack

- Backend: FastAPI + Uvicorn
- Frontend: single-page HTML/CSS/JS
- Transcription + translation: `google-genai` with Gemini Flash models
- English/Russian TTS: Kokoro local CPU TTS
- Uzbek TTS primary: Sayro `uzlm/sayro-tts-1.7B`
- Uzbek TTS fallback: Meta MMS `facebook/mms-tts-uzb-script_cyrillic`
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
|   |-- tts_router.py
|   |-- tts_kokoro.py
|   |-- tts_sayro.py
|   |-- tts_mms.py
|   |-- timing.py
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

The first Uzbek run downloads the Sayro and MMS models from Hugging Face into the normal Hugging Face cache. Sayro is a large model and may require accepting the model terms on Hugging Face before it can download.

For Sayro, accept access on Hugging Face and either run `huggingface-cli login` or add an `HF_TOKEN` value to `.env`. Without that access, the app automatically uses the MMS fallback.

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

To run without a visible Python console window on Windows:

```powershell
.\start_server_hidden.ps1
```

To stop the background server:

```powershell
.\stop_server.ps1
```

## Models And Voices

Gemini transcription/translation fallback chain:

```env
GEMINI_TRANSCRIBE_MODELS=gemini-2.0-flash,gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite
```

TTS routing:

```text
English -> Kokoro, lang a, voice af_heart
Russian -> Kokoro, lang r, voice rf_voice
Uzbek  -> Sayro uzlm/sayro-tts-1.7B
Uzbek fallback -> facebook/mms-tts-uzb-script_cyrillic
```

References:

```text
Kokoro voices: https://huggingface.co/hexgrad/Kokoro-82M
Sayro TTS:     https://huggingface.co/uzlm/sayro-tts-1.7B
MMS fallback:  https://huggingface.co/facebook/mms-tts-uzb-script_cyrillic
```

Optional overrides:

```env
KOKORO_EN_LANG=a
KOKORO_EN_VOICE=af_heart
KOKORO_RU_LANG=r
KOKORO_RU_VOICE=rf_voice
SAYRO_MODEL=uzlm/sayro-tts-1.7B
SAYRO_DEVICE=cpu
MMS_UZ_MODEL=facebook/mms-tts-uzb-script_cyrillic
```

If Sayro fails, is unavailable, or cannot be downloaded, the app automatically uses Meta MMS for Uzbek and shows a warning in the UI. If MMS also fails for a segment, the app inserts silence for that segment and keeps the job moving.

The MMS fallback model is Cyrillic-only. The app converts Uzbek Latin text to Uzbek Cyrillic before sending text to MMS.

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
8. The TTS router selects Kokoro for English/Russian or Sayro/MMS for Uzbek.
9. FFmpeg applies chained `atempo` filters to match segment timing.
10. FFmpeg concatenates timed WAV files and silence gaps into `dubbed_audio.wav`.
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
- Sayro failures automatically fall back to MMS.
- MMS failures insert same-duration silence.
- Extreme `atempo` ratios are clamped and surfaced as warnings.
- Uploads and intermediate files are deleted after completion or failure.
