from .utils import run_command


def merge_audio_and_subtitles(video_path, dubbed_audio_path, subtitle_path, output_path, subtitle_language):
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(dubbed_audio_path),
            "-i",
            str(subtitle_path),
            "-map",
            "0:v",
            "-map",
            "1:a:0",
            "-map",
            "2",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            f"language={subtitle_language}",
            str(output_path),
        ]
    )
    return output_path
