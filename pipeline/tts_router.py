import os
from pathlib import Path

from .timing import DEFAULT_SAMPLE_RATE, create_silence, fit_audio_to_duration
from .tts_kokoro import KokoroEngine
from .tts_sayro import SayroEngine
from .utils import concat_file_line, probe_duration, run_command


def get_tts_engine(target_language: str):
    if target_language == "en":
        return KokoroEngine(lang="a", voice="af_heart")
    if target_language == "ru":
        return KokoroEngine(lang="r", voice="rf_voice")
    if target_language == "uz":
        return SayroEngine(
            primary=os.getenv("SAYRO_MODEL", "uzlm/sayro-tts-1.7B"),
            fallback=os.getenv("MMS_UZ_MODEL", "facebook/mms-tts-uzb-script_cyrillic"),
        )
    raise ValueError(f"Unsupported target language for TTS: {target_language}")


def synthesize_dubbed_audio(
    segments,
    target_language,
    work_dir,
    total_duration=None,
    progress_callback=None,
):
    work_dir = Path(work_dir)
    tts_dir = work_dir / "tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    engine = get_tts_engine(target_language)
    timeline_files = []
    warnings = []
    cursor = 0.0

    total_segments = len(segments)
    for index, segment in enumerate(segments, start=1):
        if progress_callback:
            progress_callback(index, total_segments, engine.label)

        start = max(0.0, float(segment["start_sec"]))
        end = max(start + 0.25, float(segment["end_sec"]))
        duration = end - start
        text = segment.get("translated_text") or segment.get("original_text") or ""

        if start > cursor:
            timeline_files.append(create_silence(tts_dir, index, start - cursor))
            cursor = start

        raw_audio = tts_dir / f"segment_{index:04d}.wav"
        sample_rate = DEFAULT_SAMPLE_RATE
        try:
            sample_rate, warning = engine.synthesize(text, raw_audio)
            if warning:
                warnings.append(warning)
        except Exception as exc:
            warnings.append(f"{engine.label} failed for segment {index}; inserted silence. Error: {exc}")
            raw_audio = create_silence(tts_dir, index, duration)

        fitted_audio = tts_dir / f"segment_{index:04d}_fit.wav"
        timing_warning = fit_audio_to_duration(raw_audio, fitted_audio, duration, index, sample_rate=sample_rate)
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
            str(DEFAULT_SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dubbed_audio),
        ]
    )
    return dubbed_audio, "\n".join(dedupe_warnings(warnings))


def dedupe_warnings(warnings):
    seen = set()
    unique = []
    for warning in warnings:
        if warning and warning not in seen:
            seen.add(warning)
            unique.append(warning)
    return unique
