"""Speaker-similarity worker: ECAPA-TDNN embeddings and their cosine (docs/spec/NARRATE.md, "Per-chunk QA").

Run by narrate.sim in an interpreter that has torch and speechbrain (`nix develop .#ml`); it reads one JSON request
on stdin and prints one JSON reply. It never downloads: the only weights are the registered embedding_model.ckpt
named by the request, loaded with torch.load(weights_only=True) into speechbrain's ECAPA_TDNN with strict keys.

The front end is the one speechbrain/spkrec-ecapa-voxceleb's hyperparams.yaml declares: Fbank(n_mels=80) at
16 kHz, sentence mean normalisation without std, ECAPA_TDNN(channels [1024]*4 + [3072], kernels [5,3,3,3,1],
dilations [1,2,3,4,1], attention 128, 192 dims). Inputs are mono 16-bit PCM WAV files; other rates are resampled
to 16 kHz with torchaudio. The score is speechbrain's verification cosine (dim -1, eps 1e-6).

Request: {"model": path, "threads": n, "pairs": [{"id", "a": wav, "b": wav}]}.
Reply:   {"ok": true, "scores": [{"id", "sim", "a_seconds", "b_seconds"}], "torch", "speechbrain", "threads"}.
"""

import json
import sys
import wave

RATE = 16000
HYPERPARAMS = {
    "n_mels": 80,
    "channels": [1024, 1024, 1024, 1024, 3072],
    "kernel_sizes": [5, 3, 3, 3, 1],
    "dilations": [1, 2, 3, 4, 1],
    "attention_channels": 128,
    "lin_neurons": 192,
}
MAX_THREADS = 8


def read_wav(path, torch, resample):
    with wave.open(str(path)) as w:
        channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        data = w.readframes(frames)
    if width != 2:
        raise ValueError(f"{path}: {8 * width}-bit; the SIM worker reads 16-bit PCM")
    x = torch.frombuffer(bytearray(data), dtype=torch.int16).to(torch.float32) / 32768.0
    x = x.reshape(-1, channels).mean(dim=1)
    if rate != RATE:
        x = resample(x, rate, RATE)
    return x, x.numel() / RATE


class Embedder:
    def __init__(self, model, threads):
        import torch
        from speechbrain.lobes.features import Fbank
        from speechbrain.lobes.models.ECAPA_TDNN import ECAPA_TDNN
        from speechbrain.processing.features import InputNormalization
        from torchaudio.functional import resample

        torch.set_num_threads(threads)
        self.torch, self.resample = torch, resample
        hp = HYPERPARAMS
        self.features = Fbank(n_mels=hp["n_mels"])
        self.norm = InputNormalization(norm_type="sentence", std_norm=False)
        self.model = ECAPA_TDNN(
            input_size=hp["n_mels"],
            channels=hp["channels"],
            kernel_sizes=hp["kernel_sizes"],
            dilations=hp["dilations"],
            attention_channels=hp["attention_channels"],
            lin_neurons=hp["lin_neurons"],
        )
        state = torch.load(model, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        self.cache = {}

    def embed(self, path):
        if path not in self.cache:
            torch = self.torch
            wav, seconds = read_wav(path, torch, self.resample)
            with torch.no_grad():
                batch = wav.unsqueeze(0)
                lengths = torch.ones(1)
                feats = self.norm(self.features(batch), lengths)
                emb = self.model(feats, lengths).squeeze()
            self.cache[path] = (emb, seconds)
        return self.cache[path]

    def score(self, a, b):
        ea, sa = self.embed(a)
        eb, sb = self.embed(b)
        cos = self.torch.nn.functional.cosine_similarity(ea, eb, dim=-1, eps=1e-6)
        return round(float(cos), 4), round(sa, 3), round(sb, 3)


def main():
    request = json.loads(sys.stdin.read())
    threads = max(1, min(MAX_THREADS, int(request.get("threads", 4))))
    try:
        embedder = Embedder(request["model"], threads)
        scores = []
        for pair in request["pairs"]:
            sim, sa, sb = embedder.score(pair["a"], pair["b"])
            scores.append({"id": pair["id"], "sim": sim, "a_seconds": sa, "b_seconds": sb})
    except (OSError, ValueError, RuntimeError, KeyError, wave.Error, EOFError) as error:
        print(json.dumps({"ok": False, "reason": f"{type(error).__name__}: {str(error)[:500]}"}))
        return 1
    import speechbrain
    import torch

    print(
        json.dumps(
            {
                "ok": True,
                "scores": scores,
                "torch": torch.__version__,
                "speechbrain": speechbrain.__version__,
                "threads": threads,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
