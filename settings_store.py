import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


APP_NAME = "VideoTranslationStudio"
SETTINGS_FILE_NAME = "settings.json"

SETTINGS_SCHEMA = {
    "gemini_api_key": {"env": "GEMINI_API_KEY", "secret": True, "default": ""},
    "hf_token": {"env": "HF_TOKEN", "secret": True, "default": ""},
    "gemini_transcribe_models": {
        "env": "GEMINI_TRANSCRIBE_MODELS",
        "secret": False,
        "default": "gemini-2.0-flash,gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash-lite",
    },
    "uzbek_tts_mode": {"env": "UZBEK_TTS_MODE", "secret": False, "default": "mms"},
    "sayro_device": {"env": "SAYRO_DEVICE", "secret": False, "default": "cpu"},
    "sayro_model": {"env": "SAYRO_MODEL", "secret": False, "default": "uzlm/sayro-tts-1.7B"},
    "mms_uz_model": {
        "env": "MMS_UZ_MODEL",
        "secret": False,
        "default": "facebook/mms-tts-uzb-script_cyrillic",
    },
    "kokoro_en_lang": {"env": "KOKORO_EN_LANG", "secret": False, "default": "a"},
    "kokoro_en_voice": {"env": "KOKORO_EN_VOICE", "secret": False, "default": "af_heart"},
    "kokoro_ru_lang": {"env": "KOKORO_RU_LANG", "secret": False, "default": "r"},
    "kokoro_ru_voice": {"env": "KOKORO_RU_VOICE", "secret": False, "default": "rf_voice"},
}


def resource_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def user_data_dir():
    appdata = os.getenv("APPDATA")
    if appdata:
        path = Path(appdata) / APP_NAME
    else:
        path = resource_dir() / ".appdata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file():
    return user_data_dir() / SETTINGS_FILE_NAME


def runtime_media_dir(name):
    path = user_data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _env_file_values():
    env_path = resource_dir() / ".env"
    if env_path.exists():
        return {key: value for key, value in dotenv_values(env_path).items() if value is not None}
    return {}


def _json_settings():
    path = settings_file()
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_runtime_settings():
    load_dotenv(dotenv_path=resource_dir() / ".env", override=False)
    merged = {}
    env_values = _env_file_values()
    json_values = _json_settings()

    for key, meta in SETTINGS_SCHEMA.items():
        env_key = meta["env"]
        value = json_values.get(key)
        if value in (None, ""):
            value = os.getenv(env_key)
        if value in (None, ""):
            value = env_values.get(env_key)
        if value in (None, ""):
            value = meta["default"]
        merged[key] = str(value) if value is not None else ""
    return merged


def apply_runtime_settings():
    settings = load_runtime_settings()
    for key, meta in SETTINGS_SCHEMA.items():
        value = settings.get(key, "")
        if value:
            os.environ[meta["env"]] = value
        else:
            os.environ.pop(meta["env"], None)
    return settings


def public_settings():
    settings = load_runtime_settings()
    payload = {}
    for key, meta in SETTINGS_SCHEMA.items():
        if meta["secret"]:
            payload[f"{key}_set"] = bool(settings.get(key))
        else:
            payload[key] = settings.get(key, meta["default"])
    return payload


def save_settings(payload):
    existing = load_runtime_settings()
    updated = {}

    for key, meta in SETTINGS_SCHEMA.items():
        incoming = payload.get(key)
        if meta["secret"]:
            updated[key] = existing.get(key, "")
            if isinstance(incoming, str) and incoming.strip():
                updated[key] = incoming.strip()
        else:
            updated[key] = (str(incoming).strip() if incoming is not None else existing.get(key, meta["default"])).strip()
            if not updated[key]:
                updated[key] = meta["default"]

    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    apply_runtime_settings()
    return public_settings()
