from pathlib import Path

from .utils import seconds_to_srt_time


def write_srt(segments, output_path):
    lines = []
    subtitle_index = 1
    for segment in segments:
        text = (segment.get("translated_text") or "").strip()
        if not text:
            continue
        start = seconds_to_srt_time(segment["start_sec"])
        end = seconds_to_srt_time(max(segment["end_sec"], segment["start_sec"] + 0.25))
        lines.extend([str(subtitle_index), f"{start} --> {end}", normalize_subtitle_text(text), ""])
        subtitle_index += 1

    output_path = Path(output_path)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def normalize_subtitle_text(text):
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())
