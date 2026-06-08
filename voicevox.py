"""Style-BERT-VITS2を使った音声合成モジュール（voicevox.pyと同じインターフェース）"""
import wave
import struct
import time
from pathlib import Path
from config import TTS_SPEAKER, TTS_SPEED, TTS_STYLE, TTS_DEVICE

_model = None
_model_sr = 44100

HF_REPO = "litagin/style_bert_vits2_jvnv"

AVAILABLE_SPEAKERS = [
    "jvnv-M1-jp",
    "jvnv-M2-jp",
    "jvnv-F1-jp",
    "jvnv-F2-jp",
]

_SPEAKER_MODEL_FILES = {
    "jvnv-M1-jp": "jvnv-M1-jp_e158_s14000.safetensors",
    "jvnv-M2-jp": "jvnv-M2-jp_e159_s17000.safetensors",
    "jvnv-F1-jp": "jvnv-F1-jp_e160_s14000.safetensors",
    "jvnv-F2-jp": "jvnv-F2_e166_s20000.safetensors",
}


def _patch_safetensors_fp32():
    """
    safetensors.safe_open をラップして float16/bfloat16 テンソルを
    float32 に変換する。SBV2 インポート前に呼ぶこと。
    CPUではfloat16演算が未サポートのためこの変換が必要。
    """
    import torch
    import safetensors as _st

    _orig_safe_open = _st.safe_open

    class _FP32SafeOpen:
        def __init__(self, filename, framework, device="cpu"):
            self._f = _orig_safe_open(filename, framework=framework, device=device)

        def __enter__(self):
            self._f.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._f.__exit__(exc_type, exc_val, exc_tb)

        def keys(self):
            return self._f.keys()

        def get_tensor(self, key):
            t = self._f.get_tensor(key)
            if t.dtype in (torch.float16, torch.bfloat16):
                return t.to(torch.float32)
            return t

        def get_slice(self, key):
            # get_slice は通常使われないが念のため委譲
            return self._f.get_slice(key)

    _st.safe_open = _FP32SafeOpen
    print("  safetensors.safe_open float32パッチを適用しました")


def _load_model(speaker: str = TTS_SPEAKER):
    global _model, _model_sr

    if _model is not None:
        return _model, _model_sr

    import torch
    torch.set_default_dtype(torch.float32)

    # SBV2インポート前にsafe_openをパッチ（SBV2内部がfloat16モデルを
    # float32として読み込むようになる）
    _patch_safetensors_fp32()

    try:
        from style_bert_vits2.nlp import bert_models
        from style_bert_vits2.constants import Languages
        from style_bert_vits2.tts_model import TTSModel
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError(
            "style-bert-vits2 が未インストールです。\n"
            "pip install style-bert-vits2 soundfile huggingface-hub を実行してください。"
        )

    model_filename = _SPEAKER_MODEL_FILES.get(speaker, f"{speaker}_e158_s14000.safetensors")
    print(f"  モデルダウンロード中: {speaker} （初回のみ）...")
    model_file  = hf_hub_download(HF_REPO, f"{speaker}/{model_filename}")
    config_file = hf_hub_download(HF_REPO, f"{speaker}/config.json")
    style_file  = hf_hub_download(HF_REPO, f"{speaker}/style_vectors.npy")

    print("  日本語BERTモデル読み込み中...")
    bert_models.load_model(Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm")
    bert_models.load_tokenizer(Languages.JP, "ku-nlp/deberta-v2-large-japanese-char-wwm")

    _model = TTSModel(
        model_path=model_file,
        config_path=config_file,
        style_vec_path=style_file,
        device=TTS_DEVICE,
    )

    # 明示的にロードしてネットワーク構造を確保する（可能な場合）
    print("  モデルウェイトをロード中...")
    try:
        _model.load()
        print("  load() 完了")
    except Exception as e:
        print(f"  load() でエラー（infer時に自動ロードされます）: {e}")

    # net_g またはその他の nn.Module 属性を float32 に変換
    converted = False
    for attr_name, obj in vars(_model).items():
        if isinstance(obj, torch.nn.Module):
            obj.float()
            print(f"  ✅ _model.{attr_name} を float32 に変換完了")
            converted = True
    if not converted:
        print(f"  デバッグ: model attrs = {list(vars(_model).keys())}")

    print(f"  ✅ TTSモデル準備完了: {speaker}")
    return _model, _model_sr


def synthesize(text: str, output_path: str,
               speaker: str = TTS_SPEAKER,
               speed: float = TTS_SPEED,
               style: str = TTS_STYLE,
               **_kwargs) -> float:
    import soundfile as sf
    import torch

    model, _ = _load_model(speaker)

    try:
        sr, audio = model.infer(
            text=text,
            style=style,
            length=1.0 / speed,
        )
    except RuntimeError as e:
        err_str = str(e)
        if "Half" in err_str or "should be the same" in err_str or "dtype" in err_str.lower():
            # フォールバック: infer後にロードされたnet_gをfloat32に変換して再試行
            print(f"  float dtype エラー。全nn.Moduleをfloat32に変換して再試行...")
            for attr_name, obj in vars(model).items():
                if isinstance(obj, torch.nn.Module):
                    obj.float()
                    print(f"  ✅ {attr_name}.float() 完了")
            sr, audio = model.infer(text=text, style=style, length=1.0 / speed)
        else:
            raise

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, sr, subtype="PCM_16")
    return _get_wav_duration(output_path)


def synthesize_batch(lines: list[str], output_dir: str,
                     speaker: str = TTS_SPEAKER,
                     speed: float = TTS_SPEED,
                     **_kwargs) -> list[tuple[str, float]]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    _load_model(speaker)

    results = []
    for i, line in enumerate(lines):
        wav_path = str(Path(output_dir) / f"audio_{i:03d}.wav")
        if not line.strip():
            _write_silence(wav_path, 0.5)
            results.append((wav_path, 0.5))
            continue

        t0 = time.time()
        duration = synthesize(line, wav_path, speaker=speaker, speed=speed)
        elapsed = time.time() - t0
        results.append((wav_path, duration))
        print(f"  [{i+1}/{len(lines)}] {line[:25]}... → {duration:.2f}s  ({elapsed:.1f}s)")

    return results


def _get_wav_duration(wav_path: str) -> float:
    with wave.open(wav_path, "r") as wf:
        return wf.getnframes() / wf.getframerate()


def _write_silence(output_path: str, duration: float, sample_rate: int = 44100):
    num_frames = int(sample_rate * duration)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_frames, *([0] * num_frames)))
