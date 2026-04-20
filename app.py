import asyncio
import json
import logging
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from pipeline.chunk_audio import chunk_audio
from pipeline.extract_audio import extract_audio
from pipeline.merge_video import merge_audio_and_subtitles
from pipeline.subtitles import write_srt
from pipeline.text_to_speech import synthesize_dubbed_audio
from pipeline.transcribe_translate import transcribe_translate_chunks
from pipeline.utils import ensure_ffmpeg, probe_duration, safe_unlink


load_dotenv()

logger = logging.getLogger("video_dubbing")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
CHUNK_DIR = UPLOAD_DIR / "chunks"

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
SUPPORTED_LANGUAGES = {"en": "English", "ru": "Russian", "uz": "Uzbek"}

for folder in (UPLOAD_DIR, OUTPUT_DIR, CHUNK_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Video Translation and Dubbing")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

jobs = {}
uploaded_files = {}
jobs_lock = threading.Lock()


def now_ts():
    return int(time.time())


def update_job(job_id, **changes):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.update(changes)
        job["updated_at"] = now_ts()
        job["revision"] = job.get("revision", 0) + 1


def public_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job_id,
            "status": job["status"],
            "step": job.get("step"),
            "progress": job.get("progress", 0),
            "message": job.get("message", ""),
            "warning": job.get("warning", ""),
            "downloads": job.get("downloads", {}),
            "revision": job.get("revision", 0),
        }


def allowed_video(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def secure_filename(filename):
    name = Path(filename).name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_.-]", "", name)
    return name.strip("._") or "upload"


def cleanup_upload(file_id):
    upload_path = uploaded_files.pop(file_id, None)
    if upload_path:
        safe_unlink(upload_path)


def cleanup_intermediates(work_dir):
    work_dir = Path(work_dir)
    for name in ("full_audio.mp3", "dubbed_audio.wav"):
        safe_unlink(work_dir / name)
    for folder_name in ("speech_chunks", "tts_segments"):
        shutil.rmtree(work_dir / folder_name, ignore_errors=True)


def cleanup_job_if_finished(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        paths = [Path(p) for p in job.get("artifact_paths", {}).values()]
        if all(not path.exists() for path in paths):
            work_dir = Path(job["work_dir"])
            shutil.rmtree(work_dir, ignore_errors=True)
            jobs.pop(job_id, None)


def process_job(job_id, file_id, video_path, source_language, target_language):
    work_dir = OUTPUT_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    warnings = []

    try:
        update_job(
            job_id,
            status="running",
            step="Extracting audio",
            progress=8,
            message="Extracting high-quality MP3 audio with FFmpeg.",
        )
        ensure_ffmpeg()
        audio_path = extract_audio(video_path, work_dir)
        video_duration = probe_duration(video_path)

        update_job(
            job_id,
            step="Chunking",
            progress=18,
            message="Splitting audio into 55-second chunks with a 2-second overlap.",
        )
        chunks = chunk_audio(audio_path, work_dir)
        if not chunks:
            raise RuntimeError("No audio chunks were produced.")

        def transcribe_progress(current, total):
            progress = 24 + int((current / max(total, 1)) * 38)
            update_job(
                job_id,
                step="Transcribing & translating",
                progress=progress,
                message=f"Transcribing and translating chunk {current} of {total} with Gemini.",
            )

        update_job(
            job_id,
            step="Transcribing & translating",
            progress=22,
            message=f"Transcribing and translating chunk 1 of {len(chunks)} with Gemini.",
        )
        translated_segments, gemini_warnings = transcribe_translate_chunks(
            chunks,
            source_language,
            target_language,
            progress_callback=transcribe_progress,
        )
        warnings.extend(gemini_warnings)
        for warning in gemini_warnings:
            logger.warning(warning)
        if not translated_segments:
            details = f" Details: {' '.join(gemini_warnings)}" if gemini_warnings else ""
            raise RuntimeError(f"Gemini returned no transcript. Check the source language and audio track.{details}")

        def tts_progress(current, total):
            progress = 72 + int((current / max(total, 1)) * 14)
            update_job(
                job_id,
                step="Generating dubbed audio",
                progress=progress,
                message=f"Generating dubbed audio segment {current} of {total} with Kokoro.",
            )

        update_job(job_id, step="Generating dubbed audio", progress=72, message="Generating and timing dubbed speech with Kokoro.")
        dubbed_audio_path, tts_warning = synthesize_dubbed_audio(
            translated_segments,
            target_language,
            work_dir,
            total_duration=video_duration,
            progress_callback=tts_progress,
        )
        if tts_warning:
            warnings.append(tts_warning)

        subtitle_path = work_dir / "translated_subtitles.srt"
        write_srt(translated_segments, subtitle_path)

        update_job(
            job_id,
            step="Merging video",
            progress=88,
            message="Replacing audio and embedding the SRT as a soft subtitle track.",
        )
        output_video_path = work_dir / "translated_dubbed_video.mp4"
        merge_audio_and_subtitles(video_path, dubbed_audio_path, subtitle_path, output_video_path, target_language)

        cleanup_upload(file_id)
        cleanup_intermediates(work_dir)
        update_job(
            job_id,
            status="completed",
            step="Done",
            progress=100,
            message="Your translated video is ready.",
            warning="\n".join(warnings),
            downloads={
                "video": f"/api/jobs/{job_id}/download/video",
                "subtitles": f"/api/jobs/{job_id}/download/subtitles",
            },
            artifact_paths={
                "video": str(output_video_path),
                "subtitles": str(subtitle_path),
            },
        )
    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        cleanup_upload(file_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        update_job(
            job_id,
            status="failed",
            step="Failed",
            progress=0,
            message=str(exc),
            warning="\n".join(warnings),
        )


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/languages")
def languages():
    return {"languages": SUPPORTED_LANGUAGES}


@app.post("/api/upload-chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    filename: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...),
):
    clean_upload_id = secure_filename(upload_id)
    clean_filename = secure_filename(filename)
    if not clean_upload_id or not clean_filename:
        raise HTTPException(status_code=400, detail="Missing upload metadata.")
    if not allowed_video(clean_filename):
        raise HTTPException(status_code=400, detail="Unsupported video format. Use mp4, mov, avi, or mkv.")
    if chunk_index < 0 or total_chunks < 1 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk position.")

    upload_folder = CHUNK_DIR / clean_upload_id
    upload_folder.mkdir(parents=True, exist_ok=True)
    part_path = upload_folder / f"{chunk_index:06d}.part"
    with part_path.open("wb") as destination:
        shutil.copyfileobj(chunk.file, destination)

    received = len(list(upload_folder.glob("*.part")))
    if received < total_chunks:
        return {"complete": False, "received": received, "total": total_chunks}

    file_id = str(uuid.uuid4())
    output_path = UPLOAD_DIR / f"{file_id}_{clean_filename}"
    with output_path.open("wb") as destination:
        for index in range(total_chunks):
            part = upload_folder / f"{index:06d}.part"
            if not part.exists():
                raise HTTPException(status_code=400, detail=f"Missing chunk {index + 1}.")
            with part.open("rb") as source:
                shutil.copyfileobj(source, destination)

    shutil.rmtree(upload_folder, ignore_errors=True)
    uploaded_files[file_id] = output_path
    return {"complete": True, "file_id": file_id, "filename": clean_filename}


@app.post("/api/jobs")
def create_job(payload: dict):
    file_id = payload.get("file_id")
    source_language = payload.get("source_language")
    target_language = payload.get("target_language")

    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported language selection.")
    if source_language == target_language:
        raise HTTPException(status_code=400, detail="Source and target languages must be different.")

    video_path = uploaded_files.get(file_id)
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=404, detail="Uploaded file was not found. Please upload the video again.")

    job_id = str(uuid.uuid4())
    work_dir = OUTPUT_DIR / job_id
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "step": "Queued",
            "progress": 0,
            "message": "Waiting to start.",
            "warning": "",
            "created_at": now_ts(),
            "updated_at": now_ts(),
            "revision": 0,
            "work_dir": str(work_dir),
        }

    thread = threading.Thread(
        target=process_job,
        args=(job_id, file_id, Path(video_path), source_language, target_language),
        daemon=True,
    )
    thread.start()
    return JSONResponse(public_job(job_id), status_code=202)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = public_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    async def event_stream():
        last_revision = None
        while True:
            job = public_job(job_id)
            if not job:
                yield "data: " + json.dumps({"status": "failed", "message": "Job not found."}) + "\n\n"
                return

            if job["revision"] != last_revision:
                last_revision = job["revision"]
                yield "data: " + json.dumps(job) + "\n\n"

            if job["status"] in {"completed", "failed"}:
                return

            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/download/{artifact}")
def download_artifact(job_id: str, artifact: str):
    if artifact not in {"video", "subtitles"}:
        raise HTTPException(status_code=404, detail="Unknown artifact.")

    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "completed":
            raise HTTPException(status_code=404, detail="Job is not ready.")
        artifact_path = Path(job.get("artifact_paths", {}).get(artifact, ""))

    if not artifact_path.exists():
        raise HTTPException(status_code=410, detail="This temporary file has already been downloaded or removed.")

    filename = "translated_dubbed_video.mp4" if artifact == "video" else "translated_subtitles.srt"

    def remove_after_download():
        safe_unlink(artifact_path)
        cleanup_job_if_finished(job_id)

    return FileResponse(artifact_path, filename=filename, background=BackgroundTask(remove_after_download))
