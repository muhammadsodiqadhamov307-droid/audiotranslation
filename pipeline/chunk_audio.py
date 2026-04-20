from dataclasses import dataclass
from pathlib import Path

from .utils import probe_duration, run_command


CHUNK_SECONDS = 55
OVERLAP_SECONDS = 2


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path
    start_offset: float
    duration: float


def chunk_audio(audio_path, work_dir):
    chunk_dir = Path(work_dir) / "speech_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    total_duration = probe_duration(audio_path)
    chunks = []
    index = 0
    start = 0.0

    while start < total_duration:
        duration = min(CHUNK_SECONDS + OVERLAP_SECONDS, total_duration - start)
        if duration <= 0.25:
            break

        chunk_path = chunk_dir / f"chunk_{index:03d}.mp3"
        run_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-i",
                str(audio_path),
                "-t",
                f"{duration:.3f}",
                "-q:a",
                "0",
                "-map",
                "a",
                str(chunk_path),
            ]
        )
        chunks.append(
            AudioChunk(
                index=index,
                path=chunk_path,
                start_offset=float(index * CHUNK_SECONDS),
                duration=probe_duration(chunk_path),
            )
        )
        index += 1
        start = float(index * CHUNK_SECONDS)

    return chunks
