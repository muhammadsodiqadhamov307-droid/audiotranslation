# Technical Reference: Gemini + Kokoro Video Translation And Dubbing

## 1. Purpose

This application translates and dubs uploaded videos. Users select a source language and target language, then receive a dubbed MP4 and translated SRT subtitle file.

The app uses Gemini only for transcription and translation. Voice generation is performed locally with Kokoro TTS, so the dubbing stage has no Gemini TTS quota or rate limit.

## 2. Stack

- Backend: Python, FastAPI, Uvicorn
- Frontend: static HTML, CSS, JavaScript
- AI transcription and translation: `google-genai` with Gemini Flash models
- TTS: `kokoro`, `soundfile`, `numpy`
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
GEMINI_TRANSCRIBE_MODELS=gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-3.1-flash-lite-preview
```

Optional Kokoro voice overrides:

```env
KOKORO_EN_LANG=a
KOKORO_EN_VOICE=af_heart
KOKORO_RU_LANG=r
KOKORO_RU_VOICE=rf_voice
KOKORO_UZ_LANG=r
KOKORO_UZ_VOICE=rf_voice
```

The installed `kokoro` package may not support `r` for Russian in all versions. If a configured language or voice is rejected, the app falls back to `a` / `af_heart` and reports a warning.

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
  "message": "Generating dubbed audio segment 3 of 12 with Kokoro.",
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

### Step 4: Kokoro TTS

File: `pipeline/text_to_speech.py`

Kokoro runs locally on CPU. The app initializes:

```python
KPipeline(lang_code=lang_code, device="cpu")
```

Audio is generated for each segment:

```python
for _, _, audio in pipeline(text, voice=voice, speed=1.0):
    samples.append(audio)
```

The WAV output is written with:

```python
soundfile.write(path, audio_array, 24000)
```

If Kokoro fails for a segment, the app inserts silence of the same duration and continues.

### Step 5: Timing Correction

Generated segment audio is fitted to:

```text
target_duration = end_sec - start_sec
```

FFmpeg applies chained `atempo` filters. If the ratio is above `4.0` or below `0.25`, the app clamps it and adds a warning.

### Step 6: Concatenate Dubbed Audio

Timed WAV files and silence gaps are concatenated into:

```text
dubbed_audio.wav
```

### Step 7: Generate Subtitles

File: `pipeline/subtitles.py`

The app writes valid SRT subtitles from `translated_text`.

### Step 8: Merge Final Video

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
- Kokoro segment failure inserts silence and records a warning.
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

Kokoro language support depends on the installed package and available voice files. Russian and Uzbek may require fallback behavior in the currently installed upstream package.

Uzbek TTS is low-resource across local/free engines. The app warns when Uzbek uses fallback phonetics.

Jobs are in memory and are not durable across server restarts.

