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
    planned_segments = plan_dub_timeline(segments, total_duration=total_duration)
    timeline_files = []
    dubbed_segments = []
    warnings = []
    cursor = 0.0

    total_segments = len(planned_segments)
    for index, segment in enumerate(planned_segments, start=1):
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
        timing_warning, actual_duration = fit_audio_to_duration(
            raw_audio,
            fitted_audio,
            duration,
            index,
            sample_rate=sample_rate,
        )
        if timing_warning:
            warnings.append(timing_warning)

        timeline_files.append(fitted_audio)
        actual_start = cursor
        actual_end = actual_start + actual_duration
        cursor = actual_end
        dubbed_segments.append(
            {
                "start_sec": round(actual_start, 3),
                "end_sec": round(actual_end, 3),
                "original_text": segment.get("original_text", ""),
                "translated_text": segment.get("translated_text", ""),
            }
        )

    if total_duration and total_duration > cursor:
        timeline_files.append(create_silence(tts_dir, len(segments) + 1, total_duration - cursor))
    elif total_duration and cursor > total_duration + 0.25:
        warnings.append(
            f"Dubbed speech exceeded the original video timeline by {cursor - total_duration:.2f}s "
            "because the translated speech needed more time."
        )

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
    return dubbed_audio, "\n".join(dedupe_warnings(warnings)), dubbed_segments


def dedupe_warnings(warnings):
    seen = set()
    unique = []
    for warning in warnings:
        if warning and warning not in seen:
            seen.add(warning)
            unique.append(warning)
    return unique


def plan_dub_timeline(segments, total_duration=None):
    if not segments:
        return []

    source_segments = sorted((dict(segment) for segment in segments), key=lambda item: item["start_sec"])
    speech_start = max(0.0, float(source_segments[0]["start_sec"]))
    source_end = max(float(segment["end_sec"]) for segment in source_segments)
    speech_end = max(source_end, float(total_duration or source_end))
    window = max(0.25, speech_end - speech_start)

    desired_durations = [estimate_speech_duration(segment.get("translated_text") or segment.get("original_text") or "") for segment in source_segments]
    original_gaps = []
    for index in range(len(source_segments) - 1):
        gap = float(source_segments[index + 1]["start_sec"]) - float(source_segments[index]["end_sec"])
        original_gaps.append(max(0.0, min(gap, 0.6)))

    desired_speech_time = sum(desired_durations)
    max_gap_budget = max(0.0, window - len(source_segments) * 0.9)
    gap_budget = min(sum(original_gaps), max_gap_budget)
    available_speech_time = max(len(source_segments) * 0.75, window - gap_budget)
    scale = min(1.0, available_speech_time / max(desired_speech_time, 0.001))
    scaled_durations = [max(0.75, duration * scale) for duration in desired_durations]

    remaining = max(0.0, window - sum(scaled_durations))
    gap_scale = min(1.0, remaining / max(sum(original_gaps), 0.001)) if original_gaps else 0.0
    scaled_gaps = [gap * gap_scale for gap in original_gaps]

    planned = []
    cursor = speech_start
    for index, segment in enumerate(source_segments):
        duration = scaled_durations[index]
        planned.append(
            {
                **segment,
                "start_sec": round(cursor, 3),
                "end_sec": round(cursor + duration, 3),
            }
        )
        cursor += duration
        if index < len(scaled_gaps):
            cursor += scaled_gaps[index]

    return planned


def estimate_speech_duration(text):
    text = " ".join(str(text).split())
    if not text:
        return 0.75
    words = len(text.split())
    punctuation = sum(text.count(mark) for mark in ",.;:!?")
    chars = len(text)
    return max(0.9, words * 0.34 + chars * 0.012 + punctuation * 0.14)
