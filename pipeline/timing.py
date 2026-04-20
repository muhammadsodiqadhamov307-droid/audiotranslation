import time

from .utils import atempo_filter_chain, probe_duration, run_command


DEFAULT_SAMPLE_RATE = 24000
MAX_ATEMPO_RATIO = 4.0
MAX_NATURAL_SPEEDUP = 1.65
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


def fit_audio_to_duration(
    input_path,
    output_path,
    target_duration,
    segment_index,
    sample_rate=DEFAULT_SAMPLE_RATE,
    max_speedup=MAX_NATURAL_SPEEDUP,
):
    generated_duration = max(0.05, probe_duration(input_path))
    target_duration = max(0.25, float(target_duration))
    requested_ratio = generated_duration / target_duration
    ratio = requested_ratio
    warning = ""

    if ratio > max_speedup:
        warning = (
            f"Segment {segment_index} needed {requested_ratio:.2f}x speed-up; "
            f"limited to {max_speedup:.2f}x to keep speech understandable."
        )
        ratio = max_speedup
    elif ratio > MAX_ATEMPO_RATIO:
        warning = (
            f"Segment {segment_index} timing ratio {requested_ratio:.2f} was above {MAX_ATEMPO_RATIO:.2f}; "
            "used the closest supported atempo chain."
        )
        ratio = MAX_ATEMPO_RATIO
    elif ratio < MIN_ATEMPO_RATIO:
        warning = (
            f"Segment {segment_index} timing ratio {requested_ratio:.2f} was below {MIN_ATEMPO_RATIO:.2f}; "
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
    actual_duration = generated_duration / ratio
    return warning, actual_duration
