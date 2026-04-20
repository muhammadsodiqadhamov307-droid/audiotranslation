import time

from .utils import atempo_filter_chain, probe_duration, run_command


DEFAULT_SAMPLE_RATE = 24000
MAX_ATEMPO_RATIO = 4.0
MIN_ATEMPO_RATIO = 0.25


def create_silence(folder, index, duration, sample_rate=DEFAULT_SAMPLE_RATE):
    duration = max(0.05, float(duration))
    output_path = folder / f"silence_{index:04d}_{int(time.time() * 1000)}.wav"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={sample_rate}:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def fit_audio_to_duration(input_path, output_path, target_duration, segment_index, sample_rate=DEFAULT_SAMPLE_RATE):
    generated_duration = max(0.05, probe_duration(input_path))
    target_duration = max(0.25, float(target_duration))
    ratio = generated_duration / target_duration
    warning = ""

    if ratio > MAX_ATEMPO_RATIO:
        warning = (
            f"Segment {segment_index} timing ratio {ratio:.2f} was above {MAX_ATEMPO_RATIO:.2f}; "
            "used the closest supported atempo chain."
        )
        ratio = MAX_ATEMPO_RATIO
    elif ratio < MIN_ATEMPO_RATIO:
        warning = (
            f"Segment {segment_index} timing ratio {ratio:.2f} was below {MIN_ATEMPO_RATIO:.2f}; "
            "used the closest supported atempo chain."
        )
        ratio = MIN_ATEMPO_RATIO

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-filter:a",
            atempo_filter_chain(ratio),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return warning
