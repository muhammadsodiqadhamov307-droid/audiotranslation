import numpy as np
from scipy.io import wavfile


class MMSEngine:
    def __init__(self, model_id="facebook/mms-tts-uzb-script_cyrillic"):
        self.model_id = model_id
        self.model = None
        self.tokenizer = None

    @property
    def label(self):
        return "Meta MMS"

    def load(self):
        if self.model is not None and self.tokenizer is not None:
            return

        from transformers import AutoTokenizer, VitsModel
        import torch

        self.torch = torch
        self.model = VitsModel.from_pretrained(self.model_id)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.model.eval()

    def synthesize(self, text, output_path):
        self.load()
        clean_text = " ".join(str(text).split())
        if "cyrillic" in self.model_id.lower():
            clean_text = uzbek_latin_to_cyrillic(clean_text)
        if not clean_text:
            raise ValueError("Segment text was empty.")

        inputs = self.tokenizer(clean_text, return_tensors="pt")
        if inputs["input_ids"].numel() == 0:
            raise ValueError("MMS tokenizer produced no tokens. Check Uzbek Cyrillic text conversion.")
        with self.torch.no_grad():
            output = self.model(**inputs).waveform

        waveform = output.detach().cpu().numpy()
        waveform = np.squeeze(waveform)
        wavfile.write(str(output_path), rate=self.model.config.sampling_rate, data=waveform.astype(np.float32))
        return int(self.model.config.sampling_rate), ""


def uzbek_latin_to_cyrillic(text):
    """Convert common Uzbek Latin text to Cyrillic for MMS Uzbek Cyrillic TTS."""
    source = normalize_apostrophes(str(text)).lower()
    result = []
    index = 0

    digraphs = {
        "o'": "ў",
        "g'": "ғ",
        "sh": "ш",
        "ch": "ч",
        "yo": "ё",
        "yu": "ю",
        "ya": "я",
        "ye": "е",
    }
    chars = {
        "a": "а",
        "b": "б",
        "d": "д",
        "e": "е",
        "f": "ф",
        "g": "г",
        "h": "ҳ",
        "i": "и",
        "j": "ж",
        "k": "к",
        "l": "л",
        "m": "м",
        "n": "н",
        "o": "о",
        "p": "п",
        "q": "қ",
        "r": "р",
        "s": "с",
        "t": "т",
        "u": "у",
        "v": "в",
        "x": "х",
        "y": "й",
        "z": "з",
    }

    while index < len(source):
        matched = False
        for latin, cyrillic in digraphs.items():
            if source.startswith(latin, index):
                result.append(cyrillic)
                index += len(latin)
                matched = True
                break
        if matched:
            continue

        char = source[index]
        result.append(chars.get(char, char))
        index += 1

    return "".join(result)


def normalize_apostrophes(text):
    return (
        text.replace("ʻ", "'")
        .replace("ʼ", "'")
        .replace("’", "'")
        .replace("`", "'")
        .replace("‘", "'")
    )
