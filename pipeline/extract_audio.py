from pathlib import Path

from .utils import run_command


def extract_audio(video_path, work_dir):
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    audio_path = work_dir / "full_audio.mp3"

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-q:a",
            "0",
            "-map",
            "a",
            str(audio_path),
        ]
    )
    return audio_path
