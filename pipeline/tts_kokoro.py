import os

import numpy as np
import soundfile as sf
from settings_store import apply_runtime_settings


KOKORO_SAMPLE_RATE = 24000
KOKORO_SAFE_FALLBACK = ("a", "af_heart")


class KokoroEngine:
    def __init__(self, lang, voice):
        self.lang = lang
        self.voice = voice
        self.pipeline = None
        self.warning = ""

    @property
    def label(self):
        return "Kokoro"

    def load(self):
        if self.pipeline is not None:
            return

        from kokoro import KPipeline
        apply_runtime_settings()

        lang = os.getenv(f"KOKORO_{self.lang_env_prefix}_LANG", self.lang)
        voice = os.getenv(f"KOKORO_{self.lang_env_prefix}_VOICE", self.voice)
        try:
            self.pipeline = KPipeline(lang_code=lang, device="cpu")
            self.voice = voice
        except Exception as exc:
            fallback_lang, fallback_voice = KOKORO_SAFE_FALLBACK
            self.pipeline = KPipeline(lang_code=fallback_lang, device="cpu")
            self.voice = fallback_voice
            self.warning = (
                f"Kokoro rejected lang_code={lang!r} voice={voice!r}; "
                f"using fallback lang_code={fallback_lang!r} voice={fallback_voice!r}. Error: {exc}"
            )

    @property
    def lang_env_prefix(self):
        if self.lang == "a":
            return "EN"
        if self.lang == "r":
            return "RU"
        return self.lang.upper()

    def synthesize(self, text, output_path):
        self.load()
        clean_text = " ".join(str(text).split())
        if not clean_text:
            raise ValueError("Segment text was empty.")

        samples = []
        for _, _, audio in self.pipeline(clean_text, voice=self.voice, speed=1.0):
            array = np.asarray(audio, dtype=np.float32)
            if array.size:
                samples.append(array)

        if not samples:
            raise RuntimeError("Kokoro returned no audio.")

        audio_array = np.concatenate(samples)
        sf.write(str(output_path), audio_array, KOKORO_SAMPLE_RATE)
        return KOKORO_SAMPLE_RATE, self.warning
