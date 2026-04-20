import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from .utils import atempo_filter_chain, concat_file_line, probe_duration, run_command


SAMPLE_RATE = 24000
MAX_ATEMPO_RATIO = 4.0
MIN_ATEMPO_RATIO = 0.25

VOICE_MAP = {
    "en": ("a", "af_heart"),
    "ru": ("r", "rf_voice"),
    "uz": ("r", "rf_voice"),
}
KOKORO_SAFE_FALLBACK = ("a", "af_heart")


def synthesize_dubbed_audio(
    segments,
    target_language,
    work_dir,
    voice_name=None,
    total_duration=None,
    progress_callback=None,
):
    work_dir = Path(work_dir)
    tts_dir = work_dir / "tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    timeline_files = []
    warnings = []
    cursor = 0.0
    pipeline, voice, pipeline_warning = kokoro_pipeline_for(target_language, voice_name)
    if pipeline_warning:
        warnings.append(pipeline_warning)

    if target_language == "uz":
        warnings.append("Uzbek voice uses Russian phonetics as the closest available Kokoro voice.")

    total_segments = len(segments)
    for index, segment in enumerate(segments, start=1):
        if progress_callback:
            progress_callback(index, total_segments)

        start = max(0.0, float(segment["start_sec"]))
        end = max(start + 0.25, float(segment["end_sec"]))
        duration = end - start
        text = segment.get("translated_text") or segment.get("text") or segment.get("original_text") or ""

        if start > cursor:
            timeline_files.append(create_silence(tts_dir, index, start - cursor))
            cursor = start

        raw_audio = tts_dir / f"segment_{index:04d}.wav"
        try:
            synthesize_kokoro_segment(pipeline, text, voice, raw_audio)
        except Exception as exc:
            warnings.append(f"Kokoro failed for segment {index}; inserted silence. Error: {exc}")
            raw_audio = create_silence(tts_dir, index, duration)

        fitted_audio = tts_dir / f"segment_{index:04d}_fit.wav"
        timing_warning = fit_audio_to_duration(raw_audio, fitted_audio, duration, index)
        if timing_warning:
            warnings.append(timing_warning)

        timeline_files.append(fitted_audio)
        cursor = max(end, cursor + probe_duration(fitted_audio))

    if total_duration and total_duration > cursor:
        timeline_files.append(create_silence(tts_dir, len(segments) + 1, total_duration - cursor))

    if not timeline_files:
        raise RuntimeError("No translated speech could be synthesized.")

    concat_path = tts_dir / "concat.txt"
    concat_path.write_text("".join(concat_file_line(path) for path in timeline_files), encoding="utf-8")
    dubbed_audio = work_dir / "dubbed_audio.wav"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dubbed_audio),
        ]
    )
    return dubbed_audio, "\n".join(warnings)


def kokoro_pipeline_for(target_language, voice_name=None):
    from kokoro import KPipeline

    lang_code, default_voice = VOICE_MAP[target_language]
    lang_code = os.getenv(f"KOKORO_{target_language.upper()}_LANG", lang_code)
    voice = voice_name or os.getenv(f"KOKORO_{target_language.upper()}_VOICE", default_voice)
    try:
        return KPipeline(lang_code=lang_code, device="cpu"), voice, ""
    except Exception as exc:
        fallback_lang, fallback_voice = KOKORO_SAFE_FALLBACK
        warning = (
            f"Kokoro rejected lang_code={lang_code!r} voice={voice!r}; "
            f"using fallback lang_code={fallback_lang!r} voice={fallback_voice!r}. Error: {exc}"
        )
        return KPipeline(lang_code=fallback_lang, device="cpu"), fallback_voice, warning


def synthesize_kokoro_segment(pipeline, text, voice, output_path):
    clean_text = " ".join(str(text).split())
    if not clean_text:
        raise ValueError("Segment text was empty.")

    samples = []
    for _, _, audio in pipeline(clean_text, voice=voice, speed=1.0):
        array = np.asarray(audio, dtype=np.float32)
        if array.size:
            samples.append(array)

    if not samples:
        raise RuntimeError("Kokoro returned no audio.")

    audio_array = np.concatenate(samples)
    sf.write(str(output_path), audio_array, SAMPLE_RATE)
    return output_path


def create_silence(folder, index, duration):
    duration = max(0.05, float(duration))
    output_path = folder / f"silence_{index:04d}_{int(time.time() * 1000)}.wav"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={SAMPLE_RATE}:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def fit_audio_to_duration(input_path, output_path, target_duration, segment_index):
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
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return warning
