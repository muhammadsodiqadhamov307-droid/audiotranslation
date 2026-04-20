# Technical Reference: Gemini Video Translation And Dubbing App

## 1. Purpose

This application is a local full-stack video translation and dubbing tool.

Users upload a video, select a source language, select a target language, and receive:

- A translated/dubbed MP4 video
- A downloadable SRT subtitle file
- The same subtitle file embedded into the MP4 as a soft subtitle track

The app uses Gemini API models for AI tasks and FFmpeg for local audio/video processing.

## 2. Technology Stack

Backend:

- Python
- FastAPI
- Uvicorn
- Server-Sent Events for live progress updates
- Background worker threads for processing jobs

Frontend:

- Single HTML page
- Vanilla JavaScript
- CSS only, no frontend framework

AI:

- Google Gemini API via `google-genai`
- Gemini Files API for audio chunk uploads
- Gemini text/audio generation for transcription, translation, and TTS

Media processing:

- FFmpeg
- FFprobe

Storage:

- Local filesystem only
- No database
- No cloud storage

## 3. Supported Languages

The app currently supports:

| Code | Language |
|---|---|
| `en` | English |
| `ru` | Russian |
| `uz` | Uzbek |

Supported language definitions are stored in [app.py](app.py) as:

```python
SUPPORTED_LANGUAGES = {"en": "English", "ru": "Russian", "uz": "Uzbek"}
```

## 4. Configuration

Runtime configuration is loaded from `.env` using `python-dotenv`.

Required:

```env
GEMINI_API_KEY=your_key_here
```

Optional:

```env
GEMINI_TRANSCRIBE_MODELS=gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-3.1-flash-lite-preview
GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
GEMINI_TTS_REQUEST_INTERVAL_SECONDS=7.0
GEMINI_TTS_MAX_RETRIES=6
```

The Gemini client is created in [pipeline/gemini_client.py](pipeline/gemini_client.py).

Default transcription/translation model order:

1. `gemini-2.5-flash`
2. `gemini-2.0-flash`
3. `gemini-2.5-flash-lite`
4. `gemini-2.0-flash-lite`
5. `gemini-3.1-flash-lite-preview`

Default TTS model:

```text
gemini-3.1-flash-tts-preview
```

Default TTS throttle:

```text
7 seconds between Gemini TTS requests
```

This keeps the app below a 10 requests per minute TTS quota. If Gemini still returns `429 RESOURCE_EXHAUSTED`, the app parses the retry delay and retries the request.

## 5. Runtime Directories

The backend creates these folders automatically:

```text
uploads/
uploads/chunks/
outputs/
```

Directory responsibilities:

| Directory | Purpose |
|---|---|
| `uploads/chunks/` | Temporary HTTP upload chunks |
| `uploads/` | Reconstructed uploaded video files |
| `outputs/<job_id>/` | Job-specific intermediate and final files |

Intermediate files are cleaned up after processing. Final output files are deleted after download.

## 6. Backend Architecture

Main backend file:

```text
app.py
```

Core responsibilities:

- Serve the frontend
- Accept chunked video uploads
- Start background processing jobs
- Expose job status
- Stream progress through SSE
- Serve completed downloads
- Clean up temporary files

In-memory state:

```python
jobs = {}
uploaded_files = {}
jobs_lock = threading.Lock()
```

Because state is in memory, jobs are lost if the server restarts. This is acceptable for the current no-database local app design.

## 7. API Reference

### `GET /`

Serves:

```text
static/index.html
```

### `GET /api/languages`

Returns supported language metadata.

Example response:

```json
{
  "languages": {
    "en": "English",
    "ru": "Russian",
    "uz": "Uzbek"
  }
}
```

### `POST /api/upload-chunk`

Receives one video upload chunk.

Form fields:

| Field | Type | Description |
|---|---|---|
| `upload_id` | string | Client-generated upload ID |
| `filename` | string | Original file name |
| `chunk_index` | integer | Zero-based chunk index |
| `total_chunks` | integer | Total number of chunks |
| `chunk` | file | Binary chunk data |

Allowed extensions:

```text
.mp4, .mov, .avi, .mkv
```

Partial upload response:

```json
{
  "complete": false,
  "received": 1,
  "total": 4
}
```

Completed upload response:

```json
{
  "complete": true,
  "file_id": "uuid",
  "filename": "input.mp4"
}
```

### `POST /api/jobs`

Starts a video processing job.

Request body:

```json
{
  "file_id": "uuid",
  "source_language": "en",
  "target_language": "uz"
}
```

Validation:

- `source_language` must be supported
- `target_language` must be supported
- source and target languages must not be the same
- `file_id` must refer to an uploaded file

Response:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "step": "Queued",
  "progress": 0,
  "message": "Waiting to start.",
  "warning": "",
  "downloads": {},
  "revision": 0
}
```

### `GET /api/jobs/{job_id}`

Returns current job state.

Job states:

| State | Meaning |
|---|---|
| `queued` | Job has been accepted |
| `running` | Job is processing |
| `completed` | Outputs are ready |
| `failed` | Job failed |

### `GET /api/jobs/{job_id}/events`

Streams job progress with Server-Sent Events.

Each event contains the public job state as JSON.

Example SSE payload:

```text
data: {"job_id":"...","status":"running","step":"Chunking","progress":18,"message":"Splitting audio into 55-second chunks with a 2-second overlap.","warning":"","downloads":{},"revision":2}
```

The connection closes when the job reaches `completed` or `failed`.

### `GET /api/jobs/{job_id}/download/video`

Downloads:

```text
translated_dubbed_video.mp4
```

### `GET /api/jobs/{job_id}/download/subtitles`

Downloads:

```text
translated_subtitles.srt
```

Downloaded files are deleted after response close.

## 8. Frontend Architecture

Frontend files:

```text
static/index.html
static/style.css
```

The frontend provides:

- Drag and drop video upload
- File picker fallback
- Source language dropdown
- Target language dropdown
- Disabled submit button when source equals target
- Chunked upload
- SSE progress display
- Download links after completion
- Human-readable error messages

Upload chunk size:

```javascript
const CHUNK_SIZE = 8 * 1024 * 1024;
```

Progress steps:

1. Extracting audio
2. Chunking
3. Transcribing & translating
4. Generating dubbed audio
5. Merging video

## 9. Processing Pipeline

The full pipeline is executed by `process_job()` in [app.py](app.py).

### Step 1: Extract Audio

Module:

```text
pipeline/extract_audio.py
```

Input:

```text
original video
```

Output:

```text
outputs/<job_id>/full_audio.mp3
```

FFmpeg behavior:

```bash
ffmpeg -y -i input_video -q:a 0 -map a full_audio.mp3
```

Purpose:

- Extract the audio stream
- Store it as high-quality MP3
- Reduce file size compared with raw audio

### Step 2: Chunk Audio

Module:

```text
pipeline/chunk_audio.py
```

Constants:

```python
CHUNK_SECONDS = 55
OVERLAP_SECONDS = 2
```

Each chunk starts at:

```text
chunk_index * 55 seconds
```

Each chunk duration is up to:

```text
57 seconds
```

This creates a 2-second overlap between neighboring chunks.

Chunk metadata:

```python
AudioChunk(
    index=int,
    path=Path,
    start_offset=float,
    duration=float,
)
```

### Step 3: Transcription And Translation

Module:

```text
pipeline/transcribe_translate.py
```

The app uploads each audio chunk to Gemini using the Files API:

```python
uploaded_file = client.files.upload(file=str(chunk.path))
```

Gemini receives:

- Instruction prompt
- Uploaded audio file

Gemini returns JSON only:

```json
[
  {
    "start_sec": 0.5,
    "end_sec": 2.1,
    "text": "Original speech",
    "translated_text": "Translated speech"
  }
]
```

Timestamp handling:

1. Gemini returns timestamps relative to the chunk.
2. The app adds `chunk.start_offset`.
3. The app deduplicates overlap zones.

Deduplication rule:

```text
Drop segments from chunk N+1 when start_sec is inside the leading overlap zone.
```

Implementation:

```python
overlap_boundary = segment["chunk_index"] * 55 + OVERLAP_SECONDS
if segment["chunk_index"] > 0 and segment["start_sec"] < overlap_boundary:
    continue
```

Error handling:

- Invalid JSON is retried once with a stricter prompt.
- `429 RESOURCE_EXHAUSTED` causes a backoff and model fallback.
- Failed chunks are skipped.
- Warnings are shown in the UI.

### Step 4: Gemini Text-To-Speech

Module:

```text
pipeline/text_to_speech.py
```

Default voice:

```python
DEFAULT_VOICE = "Kore"
```

Uzbek fallback voice:

```python
UZBEK_FALLBACK_VOICE = "Charon"
```

Gemini TTS returns PCM audio. The app writes it as WAV using:

```python
wave.open(...)
```

The app throttles TTS calls globally inside the Python process. This is important because the Gemini TTS quota is per model per project, not per video segment.

WAV format:

| Property | Value |
|---|---|
| Sample rate | 24000 Hz |
| Channels | 1 |
| Sample width | 2 bytes |
| Codec | PCM signed 16-bit |

### Step 5: Timing Correction

Each translated segment has:

```text
target_duration = end_sec - start_sec
```

The generated TTS audio may be shorter or longer than the target duration. FFmpeg applies `atempo` to fit timing.

Speed-up cap:

```python
MAX_SPEECH_SPEEDUP = 1.35
```

This prevents the dubbed speech from becoming unnaturally fast. If translated text is much longer than the original speech, the audio may run slightly past the original segment instead of being heavily compressed.

The `atempo` filter only supports values from `0.5` to `2.0`, so the app chains filters when needed.

Example:

```text
atempo=2.0,atempo=1.5
```

### Step 6: Concatenate Dubbed Audio

The app creates:

```text
outputs/<job_id>/dubbed_audio.wav
```

It inserts silence when there are gaps between speech segments.

Silence generation uses FFmpeg:

```bash
ffmpeg -f lavfi -i anullsrc=r=24000:cl=mono -t <duration> -c:a pcm_s16le silence.wav
```

### Step 7: Generate Subtitles

Module:

```text
pipeline/subtitles.py
```

Output:

```text
outputs/<job_id>/translated_subtitles.srt
```

SRT format:

```srt
1
00:00:00,510 --> 00:00:02,010
Translated text here
```

The app uses `translated_text` and the final segment timestamps.

### Step 8: Merge Final Video

Module:

```text
pipeline/merge_video.py
```

Output:

```text
outputs/<job_id>/translated_dubbed_video.mp4
```

FFmpeg command structure:

```bash
ffmpeg -y \
  -i original_video \
  -i dubbed_audio.wav \
  -i translated_subtitles.srt \
  -map 0:v \
  -map 1:a:0 \
  -map 2 \
  -c:v copy \
  -c:a aac \
  -c:s mov_text \
  -metadata:s:s:0 language=<target_language> \
  output.mp4
```

Important:

- The original video stream is copied with `-c:v copy`.
- The original audio is replaced by the dubbed audio.
- Subtitles are embedded as a soft MP4 subtitle track using `mov_text`.
- The app does not use `-shortest`, because that can cut the output video if dubbed audio is shorter than the source video.

## 10. Job State Model

Public job object:

```json
{
  "job_id": "uuid",
  "status": "running",
  "step": "Transcribing & translating",
  "progress": 42,
  "message": "Transcribing and translating chunk 1 of 3 with Gemini.",
  "warning": "",
  "downloads": {},
  "revision": 3
}
```

The `revision` value increments whenever job state changes. The SSE endpoint uses it to avoid sending duplicate progress events.

## 11. Error Handling

Common failures:

| Failure | Cause | User-visible behavior |
|---|---|---|
| Unsupported file type | File extension is not allowed | Upload error |
| Same source and target language | Invalid request | Button disabled and backend rejects |
| Missing FFmpeg | `ffmpeg` or `ffprobe` not in PATH | Job failure |
| Gemini `429 RESOURCE_EXHAUSTED` | Quota, rate limit, or temporary capacity | Model fallback; warning if all fail |
| Invalid Gemini JSON | Model response was not parseable | Retry once with stricter prompt |
| TTS unsupported for Uzbek | Gemini TTS may not support Uzbek voice output | Retry with neutral fallback voice |
| No transcript | Gemini produced no usable segments | Job failure |

## 12. Cleanup Behavior

After successful processing:

- Original uploaded video is deleted.
- `full_audio.mp3` is deleted.
- `dubbed_audio.wav` is deleted after final merge.
- `speech_chunks/` is deleted.
- `tts_segments/` is deleted.
- Final MP4 and SRT remain until downloaded.

After failure:

- Original uploaded video is deleted.
- Job output directory is deleted.
- Job remains in memory with failure status until the server restarts.

After artifact download:

- The downloaded file is deleted.
- When both final artifacts are gone, the job directory is removed.

## 13. Known Limitations

Gemini-only transcription timing is approximate.

Gemini audio understanding can produce timestamps, but it is not a dedicated speech alignment engine. Subtitle and dubbing timing may be less precise than Google Speech-to-Text or forced-alignment tools.

Translation length can change speech timing.

Some target languages, especially Uzbek, may require more words than the source sentence. If translated text is too long for the original time window, the app caps speed-up to avoid unnatural speech. This improves voice quality but may reduce sync accuracy.

Gemini TTS language support is limited.

Uzbek TTS may fail or sound non-native. The app retries with a fallback voice and shows a warning.

The app is single-process.

Jobs are stored in memory. Multiple Uvicorn workers are not supported without replacing the in-memory job store with Redis, a database, or another shared state system.

No authentication.

The app is intended for local use. Do not expose it publicly without adding authentication, upload limits, rate limiting, and cleanup policies.

## 14. Operational Notes

Run locally:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app:app --reload --port 8000
```

Recommended production-like local run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Check FFmpeg:

```powershell
ffmpeg -version
ffprobe -version
```

Check logs:

```powershell
Get-Content uvicorn.out.log -Tail 50
Get-Content uvicorn.err.log -Tail 50
```

Stop the server by PID:

```powershell
Stop-Process -Id <pid> -Force
```

## 15. Security Notes

Do not commit:

- `.env`
- Gemini API keys
- Uploaded videos
- Output videos

If an API key is shown in a screenshot or shared accidentally, rotate it in Google AI Studio.

The upload endpoint writes files to disk. For public deployment, add:

- Maximum upload size enforcement
- User authentication
- Virus scanning if needed
- Per-user job isolation
- Background cleanup for abandoned uploads
- Persistent job tracking
