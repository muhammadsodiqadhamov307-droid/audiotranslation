import os

from dotenv import load_dotenv
from google import genai


def gemini_client():
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
    if len(api_key) < 20:
        raise RuntimeError("GEMINI_API_KEY looks too short. Paste the full key from Google AI Studio into .env.")
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
