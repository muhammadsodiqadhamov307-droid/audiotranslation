import os

import numpy as np
import soundfile as sf

from .tts_mms import MMSEngine


class SayroEngine:
    def __init__(
        self,
        primary="uzlm/sayro-tts-1.7B",
        fallback="facebook/mms-tts-uzb-script_cyrillic",
    ):
        self.primary = primary
        self.fallback = fallback
        self.model = None
        self.fallback_engine = MMSEngine(fallback)
        self._load_error = None
        self.used_mms_fallback = False

    @property
    def label(self):
        return "Sayro Uzbek TTS"

    def load(self):
        if self.model is not None:
            return
        if self._load_error is not None:
            raise self._load_error

        try:
            import torch
            from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel

            device = os.getenv("SAYRO_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")
            dtype = torch.bfloat16
            self.torch = torch
            self.model = Qwen3TTSModel.from_pretrained(
                self.primary,
                device_map=device,
                dtype=dtype,
            )
        except Exception as exc:
            self._load_error = exc
            raise

    def synthesize(self, text, output_path):
        clean_text = clean_uzbek(text)
        try:
            self.load()
            with self.torch.inference_mode():
                wavs, sample_rate = self.model.generate_custom_voice(
                    text=[clean_text],
                    speaker=["sayro"],
                    instruct=["Neutral"],
                )
            audio = wavs[0]
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            audio = np.asarray(audio, dtype=np.float32).squeeze()
            rate = int(sample_rate[0] if isinstance(sample_rate, (list, tuple)) else sample_rate)
            sf.write(str(output_path), audio, rate)
            return rate, ""
        except Exception as exc:
            self.used_mms_fallback = True
            sample_rate, warning = self.fallback_engine.synthesize(clean_text, output_path)
            details = f"Sayro TTS unavailable - used Meta MMS fallback for Uzbek voice. Error: {exc}"
            if warning:
                details = f"{details}\n{warning}"
            return sample_rate, details


def clean_uzbek(text):
    clean_text = " ".join(str(text).split())
    try:
        from uzbek_normalizer import clean_uzbek_text

        return clean_uzbek_text(clean_text)
    except Exception:
        return clean_text
