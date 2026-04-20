import os

from google import genai


def gemini_client():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
    return genai.Client(api_key=api_key)


def transcription_model():
    return transcription_models()[0]


def transcription_models():
    configured = os.getenv("GEMINI_TRANSCRIBE_MODELS") or os.getenv("GEMINI_TRANSCRIBE_MODEL")
    if configured:
        models = [model.strip() for model in configured.split(",") if model.strip()]
        if models:
            return models
    return [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-3.1-flash-lite-preview",
    ]


def tts_model():
    return os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")


def tts_request_interval_seconds():
    return float(os.getenv("GEMINI_TTS_REQUEST_INTERVAL_SECONDS", "7.0"))


def tts_max_retries():
    return int(os.getenv("GEMINI_TTS_MAX_RETRIES", "6"))
