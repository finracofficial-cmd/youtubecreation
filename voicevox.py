"""VOICEVOX HTTP APIを使った音声合成モジュール"""
import json
import time
import wave
import requests
from pathlib import Path
from config import VOICEVOX_URL, VOICEVOX_SPEAKER, VOICEVOX_SPEED


def synthesize(text: str, output_path: str, speaker: int = VOICEVOX_SPEAKER,
               speed: float = VOICEVOX_SPEED, max_retry: int = 10) -> float:
    """
    テキストをVOICEVOXで音声合成してWAVファイルに保存する。
    返り値: 生成された音声の長さ（秒）
    """
    query = None
    for _ in range(max_retry):
        try:
            r = requests.post(
                f"{VOICEVOX_URL}/audio_query",
                params={"text": text, "speaker": speaker},
                timeout=(10.0, 60.0)
            )
            r.raise_for_status()
            query = r.json()
            break
        except Exception:
            time.sleep(1)

    if query is None:
        raise RuntimeError(f"VOICEVOX audio_query 失敗: '{text}'")

    query["speedScale"] = speed
    query["prePhonemeLength"] = 0.1
    query["postPhonemeLength"] = 0.3

    wav_data = None
    for _ in range(max_retry):
        try:
            r = requests.post(
                f"{VOICEVOX_URL}/synthesis",
                params={"speaker": speaker},
                data=json.dumps(query),
                headers={"Content-Type": "application/json"},
                timeout=(10.0, 300.0)
            )
            r.raise_for_status()
            wav_data = r.content
            break
        except Exception:
            time.sleep(1)

    if wav_data is None:
        raise RuntimeError(f"VOICEVOX synthesis 失敗: '{text}'")

    Path(output_path).write_bytes(wav_data)
    return _get_wav_duration(output_path)


def _get_wav_duration(wav_path: str) -> float:
    with wave.open(wav_path, "r") as wf:
        return wf.getnframes() / wf.getframerate()


def get_speakers() -> list[dict]:
    """利用可能なスピーカー一覧を取得する"""
    r = requests.get(f"{VOICEVOX_URL}/speakers", timeout=10)
    r.raise_for_status()
    return r.json()


def synthesize_batch(lines: list[str], output_dir: str,
                     speaker: int = VOICEVOX_SPEAKER,
                     speed: float = VOICEVOX_SPEED) -> list[tuple[str, float]]:
    """
    複数行のテキストを一括音声合成する。
    返り値: [(wavファイルパス, 秒数), ...]
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = []
    for i, line in enumerate(lines):
        if not line.strip():
            # 空行はスキップ（0.5秒の無音を挿入）
            wav_path = str(Path(output_dir) / f"audio_{i:03d}.wav")
            _write_silence(wav_path, 0.5)
            results.append((wav_path, 0.5))
            continue
        wav_path = str(Path(output_dir) / f"audio_{i:03d}.wav")
        duration = synthesize(line, wav_path, speaker=speaker, speed=speed)
        results.append((wav_path, duration))
        print(f"  [{i+1}/{len(lines)}] '{line[:20]}...' → {duration:.2f}s")
    return results


def _write_silence(output_path: str, duration: float, sample_rate: int = 24000):
    """指定秒数の無音WAVを生成する"""
    import struct
    num_frames = int(sample_rate * duration)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_frames, *([0] * num_frames)))
