"""AivisSpeech Engine HTTP APIを使った音声合成モジュール"""
import time
import wave
import struct
import requests
from pathlib import Path
from config import TTS_ENGINE_URL, TTS_SPEAKER_NAME, TTS_STYLE_NAME, TTS_SPEED

AVAILABLE_SPEAKERS = ["阿井田 茂"]

_style_id_cache: dict[tuple, int] = {}


def _get_style_id(speaker_name: str = TTS_SPEAKER_NAME,
                  style_name: str = TTS_STYLE_NAME) -> int:
    """話者名とスタイル名からスタイルIDを取得する"""
    key = (speaker_name, style_name)
    if key in _style_id_cache:
        return _style_id_cache[key]

    r = requests.get(f"{TTS_ENGINE_URL}/speakers", timeout=30)
    r.raise_for_status()
    speakers = r.json()

    for speaker in speakers:
        if speaker["name"] == speaker_name:
            for style in speaker["styles"]:
                if style["name"] == style_name:
                    _style_id_cache[key] = style["id"]
                    print(f"  スタイルID: {speaker_name}/{style_name} → {style['id']}")
                    return style["id"]
            # スタイル名が見つからなければ最初のスタイルを使う
            first_id = speaker["styles"][0]["id"]
            print(f"  ⚠️ スタイル '{style_name}' が見つからず → {speaker['styles'][0]['name']} (ID={first_id}) を使用")
            _style_id_cache[key] = first_id
            return first_id

    raise ValueError(
        f"話者 '{speaker_name}' が見つかりません。"
        f"利用可能: {[s['name'] for s in speakers]}"
    )


def synthesize(text: str, output_path: str,
               speaker: str = TTS_SPEAKER_NAME,
               speed: float = TTS_SPEED,
               style: str = TTS_STYLE_NAME,
               **_kwargs) -> float:
    """テキストを音声合成してWAVファイルに保存する。戻り値は秒数。"""
    style_id = _get_style_id(speaker, style)

    # audio_query
    r = requests.post(
        f"{TTS_ENGINE_URL}/audio_query",
        params={"speaker": style_id, "text": text},
        timeout=60
    )
    r.raise_for_status()
    query = r.json()

    # 速度調整
    query["speedScale"] = speed

    # synthesis
    r = requests.post(
        f"{TTS_ENGINE_URL}/synthesis",
        params={"speaker": style_id},
        json=query,
        timeout=120
    )
    r.raise_for_status()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(r.content)

    return _get_wav_duration(output_path)


def synthesize_batch(lines: list[str], output_dir: str,
                     speaker: str = TTS_SPEAKER_NAME,
                     speed: float = TTS_SPEED,
                     **_kwargs) -> list[tuple[str, float]]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

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
        print(f"  [{i+1}/{len(lines)}] {line[:25]}... → {duration:.2f}s ({elapsed:.1f}s)")

    return results


def _get_wav_duration(wav_path: str) -> float:
    with wave.open(wav_path, "r") as wf:
        return wf.getnframes() / wf.getframerate()


def _write_silence(output_path: str, duration: float, sample_rate: int = 24000):
    num_frames = int(sample_rate * duration)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_frames, *([0] * num_frames)))
