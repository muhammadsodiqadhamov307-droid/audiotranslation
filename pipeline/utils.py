import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def ensure_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FFmpegError("FFmpeg and FFprobe must be installed and available on PATH.")


def run_command(command, *, cwd=None):
    ensure_ffmpeg()
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise FFmpegError(f"Command failed: {' '.join(map(str, command))}\n{detail}")
    return completed


def probe_duration(path):
    ensure_ffmpeg()
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise FFmpegError(f"Could not read media duration: {completed.stderr.strip()}")
    try:
        return max(0.0, float(completed.stdout.strip()))
    except ValueError as exc:
        raise FFmpegError(f"Invalid duration returned by ffprobe for {path}") from exc


def atempo_filter_chain(tempo):
    tempo = max(0.05, min(20.0, float(tempo)))
    filters = []
    while tempo < 0.5:
        filters.append("atempo=0.5")
        tempo /= 0.5
    while tempo > 2.0:
        filters.append("atempo=2.0")
        tempo /= 2.0
    filters.append(f"atempo={tempo:.6f}")
    return ",".join(filters)


def concat_file_line(path):
    normalized = Path(path).resolve().as_posix().replace("'", "'\\''")
    return f"file '{normalized}'\n"


def seconds_to_srt_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    if milliseconds == 1000:
        milliseconds = 0
        whole_seconds += 1
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def safe_unlink(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
