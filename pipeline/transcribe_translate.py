import json
import re
import time

from google.genai import types

from .chunk_audio import OVERLAP_SECONDS, AudioChunk
from .gemini_client import gemini_client, transcription_models


LANGUAGE_NAMES = {
    "en": "English",
    "ru": "Russian",
    "uz": "Uzbek",
}


def transcribe_translate_chunks(chunks, source_language, target_language, progress_callback=None):
    client = gemini_client()
    segments = []
    warnings = []
    total = len(chunks)

    for position, chunk in enumerate(chunks, start=1):
        if progress_callback:
            progress_callback(position, total)

        try:
            chunk_segments = process_chunk_with_retry(client, chunk, source_language, target_language)
        except Exception as exc:
            warnings.append(f"Gemini skipped chunk {position} after retry: {exc}")
            continue

        for segment in chunk_segments:
            normalized = normalize_segment(segment, chunk)
            if normalized:
                segments.append(normalized)

    return deduplicate_overlap_segments(segments), warnings


def process_chunk_with_retry(client, chunk, source_language, target_language):
    last_error = None
    models = transcription_models()
    for model_index, model in enumerate(models):
        for attempt in range(2):
            try:
                prompt = build_prompt(source_language, target_language, strict=attempt > 0)
                return transcribe_translate_chunk(client, chunk, prompt, model)
            except Exception as exc:
                last_error = exc
                if is_resource_exhausted(exc):
                    time.sleep(min(8 * (attempt + 1) * (model_index + 1), 30))
                    break
                time.sleep(2)
    raise last_error


def transcribe_translate_chunk(client, chunk: AudioChunk, prompt, model):
    uploaded_file = client.files.upload(file=str(chunk.path))
    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt, uploaded_file],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        return parse_json_array(response.text)
    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass


def is_resource_exhausted(exc):
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "resource exhausted" in text


def build_prompt(source_language, target_language, strict=False):
    source_name = LANGUAGE_NAMES[source_language]
    target_name = LANGUAGE_NAMES[target_language]
    strict_note = (
        "Your previous response was invalid. Return a raw JSON array only. "
        "Do not include markdown fences, prose, comments, trailing commas, or schema text.\n"
        if strict
        else ""
    )
    return (
        strict_note
        + f"Transcribe this audio in {source_name}. "
        + "Return a JSON array where each element has start_sec as a float, "
        + "end_sec as a float, text as a string, and translated_text as a string. "
        + f"Translate each text segment into {target_name}. "
        + "Use timestamps relative to the beginning of this audio chunk. "
        + "Keep segments short enough for subtitles: split long speech into multiple segments, "
        + "avoid putting more than one sentence in a segment, and do not assign long translated text to a very short time range. "
        + "Return ONLY valid JSON, no markdown, no explanation."
    )


def parse_json_array(text):
    if not text:
        raise ValueError("Gemini returned an empty response.")

    cleaned = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response did not contain a JSON array.")

    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("Gemini response JSON was not an array.")
    return parsed


def normalize_segment(segment, chunk: AudioChunk):
    try:
        start = max(0.0, float(segment["start_sec"])) + chunk.start_offset
        end = max(0.0, float(segment["end_sec"])) + chunk.start_offset
    except (KeyError, TypeError, ValueError):
        return None

    text = str(segment.get("text", "")).strip()
    translated_text = str(segment.get("translated_text", "")).strip()
    if not text and not translated_text:
        return None

    if end <= start:
        end = start + 0.25

    return {
        "chunk_index": chunk.index,
        "start_sec": round(start, 3),
        "end_sec": round(end, 3),
        "text": text,
        "translated_text": translated_text or text,
    }


def deduplicate_overlap_segments(segments):
    deduped = []
    for segment in sorted(segments, key=lambda item: (item["start_sec"], item["chunk_index"])):
        overlap_boundary = segment["chunk_index"] * 55 + OVERLAP_SECONDS
        if segment["chunk_index"] > 0 and segment["start_sec"] < overlap_boundary:
            continue
        segment.pop("chunk_index", None)
        deduped.append(segment)
    return deduped
