import base64
import re
import threading
import time
import wave
from pathlib import Path

from google.genai import types

from .gemini_client import gemini_client, tts_max_retries, tts_model, tts_request_interval_seconds
from .utils import atempo_filter_chain, concat_file_line, probe_duration, run_command


DEFAULT_VOICE = "Kore"
UZBEK_FALLBACK_VOICE = "Charon"
WAV_RATE = 24000
WAV_CHANNELS = 1
WAV_SAMPLE_WIDTH = 2
MAX_SPEECH_SPEEDUP = 1.35

_tts_rate_lock = threading.Lock()
_last_tts_request_at = 0.0


def synthesize_dubbed_audio(segments, target_language, work_dir, voice_name=None, total_duration=None):
    client = gemini_client()
    work_dir = Path(work_dir)
    tts_dir = work_dir / "tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    timeline_files = []
    warning = ""
    cursor = 0.0

    for index, segment in enumerate(segments, start=1):
        start = max(0.0, float(segment["start_sec"]))
        end = max(start + 0.25, float(segment["end_sec"]))
        text = segment.get("translated_text") or segment.get("text") or ""
        if not text.strip():
            continue

        if start > cursor:
            timeline_files.append(create_silence(tts_dir, index, start - cursor))
            cursor = start

        raw_audio = tts_dir / f"segment_{index:04d}.wav"
        try:
            synthesize_text_to_wav(client, text, raw_audio, voice_name or DEFAULT_VOICE)
        except Exception:
            if target_language != "uz":
                raise
            warning = (
                "Gemini TTS does not currently list Uzbek as a supported TTS language. "
                "This segment was retried with a neutral English voice, so pronunciation may be imperfect."
            )
            synthesize_text_to_wav(
                client,
                text,
                raw_audio,
                UZBEK_FALLBACK_VOICE,
                prompt_prefix="Read this text aloud with a neutral English voice and approximate the pronunciation clearly: ",
            )

        fitted_audio = tts_dir / f"segment_{index:04d}_fit.wav"
        fit_audio_to_duration(raw_audio, fitted_audio, end - start)
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
            str(WAV_RATE),
            "-ac",
            str(WAV_CHANNELS),
            "-c:a",
            "pcm_s16le",
            str(dubbed_audio),
        ]
    )
    return dubbed_audio, warning


def synthesize_text_to_wav(client, text, output_path, voice_name, prompt_prefix=""):
    response = generate_tts_with_retry(client, (prompt_prefix + text)[:8000], voice_name)
    pcm = extract_pcm_audio(response)
    if not pcm:
        raise RuntimeError("Gemini TTS returned no audio data.")
    write_wave_file(output_path, pcm)


def generate_tts_with_retry(client, text, voice_name):
    last_error = None
    for attempt in range(tts_max_retries() + 1):
        try:
            wait_for_tts_rate_slot()
            return client.models.generate_content(
                model=tts_model(),
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                        )
                    ),
                ),
            )
        except Exception as exc:
            last_error = exc
            if not is_resource_exhausted(exc) or attempt >= tts_max_retries():
                raise
            time.sleep(retry_delay_seconds(exc, attempt))
    raise last_error


def wait_for_tts_rate_slot():
    global _last_tts_request_at
    interval = max(0.0, tts_request_interval_seconds())
    with _tts_rate_lock:
        elapsed = time.monotonic() - _last_tts_request_at
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _last_tts_request_at = time.monotonic()


def is_resource_exhausted(exc):
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "resource exhausted" in text


def retry_delay_seconds(exc, attempt):
    text = str(exc)
    patterns = [
        r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry in (\d+(?:\.\d+)?)s",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return max(1.0, float(match.group(1)) + 1.0)
    return min(60.0, 8.0 * (attempt + 1))


def extract_pcm_audio(response):
    for candidate in response.candidates or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None)
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return base64.b64decode(data)
    return b""


def write_wave_file(path, pcm):
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(WAV_CHANNELS)
        wav_file.setsampwidth(WAV_SAMPLE_WIDTH)
        wav_file.setframerate(WAV_RATE)
        wav_file.writeframes(pcm)


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
            f"anullsrc=r={WAV_RATE}:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def fit_audio_to_duration(input_path, output_path, target_duration):
    input_duration = probe_duration(input_path)
    target_duration = max(0.25, float(target_duration))
    target_duration = max(target_duration, input_duration / MAX_SPEECH_SPEEDUP)
    tempo = input_duration / target_duration if target_duration else 1.0
    filters = atempo_filter_chain(tempo)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-filter:a",
            filters,
            "-ar",
            str(WAV_RATE),
            "-ac",
            str(WAV_CHANNELS),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
