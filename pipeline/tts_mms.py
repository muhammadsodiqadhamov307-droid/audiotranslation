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
        if not clean_text:
            raise ValueError("Segment text was empty.")

        inputs = self.tokenizer(clean_text, return_tensors="pt")
        with self.torch.no_grad():
            output = self.model(**inputs).waveform

        waveform = output.detach().cpu().numpy()
        waveform = np.squeeze(waveform)
        wavfile.write(str(output_path), rate=self.model.config.sampling_rate, data=waveform.astype(np.float32))
        return int(self.model.config.sampling_rate), ""
