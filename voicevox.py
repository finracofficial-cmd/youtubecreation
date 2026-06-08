"""Style-BERT-VITS2を使った音声合成モジュール（voicevox.pyと同じインターフェース）"""
import wave
import struct
import time
from pathlib import Path
from config import TTS_SPEAKER, TTS_SPEED, TTS_STYLE, TTS_DEVICE

# グローバルモデルキャッシュ（初回のみダウンロード・ロード）
_model = None
_model_sr = 44100

HF_REPO = "litagin/style_bert_vits2_jvnv"

AVAILABLE_SPEAKERS = [
    "jvnv-M1-jp",  # 男性1（ニュースナレーター向け）
    "jvnv-M2-jp",  # 男性2
    "jvnv-F1-jp",  # 女性1
    "jvnv-F2-jp",  # 女性2
]

# 各スピーカーのsafetensorsファイル名（リポジトリの実際のファイル名）
_SPEAKER_MODEL_FILES = {
    "jvnv-M1-jp": "jvnv-M1-jp_e158_s14000.safetensors",
    "jvnv-M2-jp": "jvnv-M2-jp_e159_s17000.safetensors",
    "jvnv-F1-jp": "jvnv-F1-jp_e160_s14000.safetensors",
    "jvnv-F2-jp": "jvnv-F2_e166_s20000.safetensors",
}


def _load_model(speaker: str = TTS_SPEAKER):
    global _model, _model_sr

    if _model is not None:
        return _model, _model_sr

    # CPU環境ではfloat16非対応のため、SBV2インポート前にfloat32をデフォルト化
    import torch
    torch.set_default_dtype(torch.float32)

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

    # SBV2モデルはlazy load（初回infer時にload）。
    # 明示的にload()を呼んでnet_gを確保し、CPUのfloat16非対応問題を解消するため
    # 全パラメータ・バッファをfloat32に変換する。
    print("  モデルウェイトをロード・float32変換中...")
    _model.load()
    if hasattr(_model, 'net_g') and _model.net_g is not None:
        _model.net_g.float()
        print("  ✅ net_g を float32 に変換完了")
    else:
        print("  ⚠️  net_g 属性が見つかりません（推論時にfloat32エラーが起きる可能性があります）")

    print(f"  ✅ TTSモデル準備完了: {speaker}")
    return _model, _model_sr


def synthesize(text: str, output_path: str,
               speaker: str = TTS_SPEAKER,
               speed: float = TTS_SPEED,
               style: str = TTS_STYLE,
               **_kwargs) -> float:
    """
    テキストをStyle-BERT-VITS2で音声合成してWAVファイルに保存する。
    返り値: 生成された音声の長さ（秒）
    """
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
            # float16/float32混在エラーをここでも拾う（フォールバック）
            print(f"  float dtype エラー検出、net_g を float32 に変換して再試行: {e}")
            if hasattr(model, 'net_g') and model.net_g is not None:
                model.net_g.float()
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
    """
    複数行のテキストを一括音声合成する。
    返り値: [(wavファイルパス, 秒数), ...]
    """
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
    """指定秒数の無音WAVを生成する（SBV2出力と同じ mono/44100 形式）"""
    num_frames = int(sample_rate * duration)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_frames, *([0] * num_frames)))
