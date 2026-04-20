# Technical Reference: Gemini, Kokoro, Sayro Video Translation And Dubbing

## 1. Purpose

This application translates and dubs uploaded videos. Users select a source language and target language, then receive a dubbed MP4 and translated SRT subtitle file.

Gemini handles transcription and translation. Voice generation runs locally: Kokoro for English and Russian, Sayro for Uzbek, and Meta MMS as the Uzbek fallback.

## 2. Stack

- Backend: Python, FastAPI, Uvicorn
- Frontend: static HTML, CSS, JavaScript
- AI transcription and translation: `google-genai` with Gemini Flash models
- English/Russian TTS: `kokoro`, `soundfile`, `numpy`
- Uzbek TTS primary: `uzlm/sayro-tts-1.7B` via `qwen_tts`
- Uzbek TTS fallback: `facebook/mms-tts-uzb-script_cyrillic` via `transformers`
- Audio/video processing: FFmpeg and FFprobe
- Storage: local filesystem only

## 3. Languages

| Code | Language |
|---|---|
| `en` | English |
| `ru` | Russian |
| `uz` | Uzbek |

## 4. Configuration

Required `.env` value:

```env
GEMINI_API_KEY=your_key_here
```

Optional Gemini model list:

```env
GEMINI_TRANSCRIBE_MODELS=gemini-2.0-flash,gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite
```

Optional TTS overrides:

```env
KOKORO_EN_LANG=a
KOKORO_EN_VOICE=af_heart
KOKORO_RU_LANG=r
KOKORO_RU_VOICE=rf_voice
SAYRO_MODEL=uzlm/sayro-tts-1.7B
SAYRO_DEVICE=cpu
MMS_UZ_MODEL=facebook/mms-tts-uzb-script_cyrillic
HF_TOKEN=your_huggingface_token_here
```

Sayro is large and may require Hugging Face access approval. If it cannot load, the app falls back to MMS. The MMS fallback model is Cyrillic-only, so the app converts Uzbek Latin text to Uzbek Cyrillic before synthesis.

## 5. Runtime Directories

```text
uploads/
uploads/chunks/
outputs/
```

`uploads/chunks/` stores temporary HTTP upload parts. `uploads/` stores reconstructed input videos. `outputs/<job_id>/` stores intermediate and final processing files.

## 6. Backend API

### `GET /`

Serves `static/index.html`.

### `GET /api/languages`

Returns supported language codes.

### `POST /api/upload-chunk`

Accepts one upload chunk with multipart form fields:

- `upload_id`
- `filename`
- `chunk_index`
- `total_chunks`
- `chunk`

Allowed extensions:

```text
.mp4, .mov, .avi, .mkv
```

### `POST /api/jobs`

Starts a background dubbing job.

Body:

```json
{
  "file_id": "uuid",
  "source_language": "en",
  "target_language": "uz"
}
```

### `GET /api/jobs/{job_id}`

Returns current job state.

### `GET /api/jobs/{job_id}/events`

Streams job progress through Server-Sent Events.

### `GET /api/jobs/{job_id}/download/video`

Downloads `translated_dubbed_video.mp4`.

### `GET /api/jobs/{job_id}/download/subtitles`

Downloads `translated_subtitles.srt`.

## 7. Job State

Jobs are stored in memory:

```python
jobs = {}
uploaded_files = {}
```

Public job state:

```json
{
  "job_id": "uuid",
  "status": "running",
  "step": "Generating dubbed audio",
  "progress": 80,
  "message": "Generating dubbed audio with Sayro Uzbek TTS: segment 3 of 12.",
  "warning": "",
  "downloads": {},
  "revision": 5
}
```

Because jobs are in memory, they are lost when the server restarts.

## 8. Processing Pipeline

### Step 1: Extract Audio

File: `pipeline/extract_audio.py`

FFmpeg extracts MP3:

```bash
ffmpeg -i input_video -q:a 0 -map a full_audio.mp3
```

### Step 2: Chunk Audio

File: `pipeline/chunk_audio.py`

Constants:

```python
CHUNK_SECONDS = 55
OVERLAP_SECONDS = 2
```

Each chunk starts at:

```text
chunk_index * 55
```

### Step 3: Gemini Transcription And Translation

File: `pipeline/transcribe_translate.py`

Each chunk is uploaded using:

```python
client.files.upload(file=str(chunk.path))
```

Gemini must return:

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

The app offsets timestamps by the chunk start offset.

Overlap deduplication:

```text
Drop segments from chunk N+1 when start_sec < previous_chunk_last_end - 2
```

### Step 4: TTS Routing

File: `pipeline/tts_router.py`

Routing:

```python
def get_tts_engine(target_language: str):
    if target_language == "en":
        return KokoroEngine(lang="a", voice="af_heart")
    if target_language == "ru":
        return KokoroEngine(lang="r", voice="rf_voice")
    if target_language == "uz":
        return SayroEngine(
            primary="uzlm/sayro-tts-1.7B",
            fallback="facebook/mms-tts-uzb-script_cyrillic",
        )
```

### Step 5: Kokoro TTS

File: `pipeline/tts_kokoro.py`

Kokoro runs locally on CPU:

```python
KPipeline(lang_code=lang_code, device="cpu")
```

WAV output is written at 24000 Hz.

### Step 6: Sayro And MMS Uzbek TTS

Files:

```text
pipeline/tts_sayro.py
pipeline/tts_mms.py
```

Sayro is tried first. Uzbek text is cleaned through `clean_uzbek_text()` when `uzbek_normalizer` is available.

If Sayro raises any exception, MMS is used automatically and the warning is sent to the UI:

```text
Sayro TTS unavailable - used Meta MMS fallback for Uzbek voice
```

If MMS also fails for a segment, the app inserts silence with the same target duration.

### Step 7: Timing Correction

File: `pipeline/timing.py`

Generated segment audio is fitted to:

```text
target_duration = end_sec - start_sec
```

FFmpeg applies chained `atempo` filters. If the ratio is above `4.0` or below `0.25`, the app clamps it and adds a warning.

### Step 8: Concatenate Dubbed Audio

Timed WAV files and silence gaps are concatenated into:

```text
dubbed_audio.wav
```

### Step 9: Generate Subtitles

File: `pipeline/subtitles.py`

The app writes valid SRT subtitles from `translated_text`.

### Step 10: Merge Final Video

File: `pipeline/merge_video.py`

FFmpeg maps:

- original video stream
- dubbed audio stream
- SRT subtitle stream

The video stream is copied with `-c:v copy`. Audio is encoded as AAC. Subtitles are embedded as `mov_text`.

The app does not use `-shortest`, because that can cut the final video when dubbed audio is shorter than the source video.

## 9. Frontend

Files:

```text
static/index.html
static/style.css
```

The frontend provides:

- Drag and drop upload
- Source and target language dropdowns
- Disabled submit button when languages match
- Chunked upload
- SSE progress
- Completion downloads
- Warning and error display

## 10. Error Handling

- Invalid upload metadata returns HTTP 400.
- Unsupported video extensions return HTTP 400.
- Same source and target language is rejected.
- Gemini invalid JSON is retried once with a stricter prompt.
- Gemini `429 RESOURCE_EXHAUSTED` triggers model fallback/backoff.
- Sayro failure uses MMS fallback.
- MMS segment failure inserts silence.
- FFmpeg failures surface through the SSE job message.

## 11. Cleanup

On success:

- Input upload is deleted.
- Audio chunks are deleted.
- TTS segment WAV files are deleted.
- Final MP4 and SRT remain until downloaded.

On failure:

- Input upload is deleted.
- Job output directory is deleted.
- Failure status remains in memory.

After download:

- Downloaded artifact is deleted.
- When both artifacts are gone, the job directory is deleted.

## 12. Operational Commands

Install:

```powershell
pip install -r requirements.txt
```

Run:

```powershell
uvicorn app:app --reload --port 8000
```

Check logs:

```powershell
Get-Content uvicorn.out.log -Tail 50
Get-Content uvicorn.err.log -Tail 50
```

Stop by PID:

```powershell
Stop-Process -Id <pid> -Force
```

## 13. Known Limitations

Gemini timestamps are approximate because Gemini is not a dedicated forced-alignment model.

Kokoro language support depends on the installed package and available voice files. Russian may require fallback behavior in the currently installed upstream package.

Sayro is a large local model. CPU inference can be slow, and the first run may take a long time because models must download and load.

Jobs are in memory and are not durable across server restarts.
