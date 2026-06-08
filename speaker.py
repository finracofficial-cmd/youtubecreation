"""
VOICEVOXスピーカー管理モジュール
.envのVOICEVOX_SPEAKERを対話的に設定する
"""
import json
import os
import requests
from pathlib import Path
from config import VOICEVOX_URL

# よく使われるスピーカーのオフライン一覧（VOICEVOXが起動していない場合のフォールバック）
KNOWN_SPEAKERS = [
    {"id": 1,  "name": "四国めたん",   "style": "あまあま"},
    {"id": 2,  "name": "四国めたん",   "style": "ノーマル"},
    {"id": 3,  "name": "ずんだもん",   "style": "ノーマル"},
    {"id": 1,  "name": "ずんだもん",   "style": "あまあま"},
    {"id": 4,  "name": "ずんだもん",   "style": "つんつん"},
    {"id": 5,  "name": "ずんだもん",   "style": "セクシー"},
    {"id": 6,  "name": "ずんだもん",   "style": "ささやき"},
    {"id": 7,  "name": "ずんだもん",   "style": "ヒソヒソ"},
    {"id": 8,  "name": "春日部つむぎ", "style": "ノーマル"},
    {"id": 9,  "name": "波音リツ",     "style": "ノーマル"},
    {"id": 10, "name": "雨晴はう",     "style": "ノーマル"},
    {"id": 11, "name": "玄野武宏",     "style": "ノーマル"},
    {"id": 12, "name": "白上虎太郎",   "style": "ふつう"},
    {"id": 13, "name": "青山龍星",     "style": "ノーマル"},
    {"id": 14, "name": "冥鳴ひまり",   "style": "ノーマル"},
    {"id": 15, "name": "九州そら",     "style": "ノーマル"},
    {"id": 16, "name": "もち子さん",   "style": "ノーマル"},
    {"id": 17, "name": "剣崎雌雄",     "style": "男性"},
    {"id": 18, "name": "WhiteCUL",     "style": "たのしい"},
    {"id": 20, "name": "後鬼",         "style": "人間Ver."},
    {"id": 23, "name": "No.7",         "style": "ノーマル"},
    {"id": 26, "name": "ちび式じい",   "style": "ノーマル"},
    {"id": 27, "name": "中国うさぎ",   "style": "ノーマル"},
    {"id": 28, "name": "栗田まろん",   "style": "ノーマル"},
    {"id": 29, "name": "あいえるたん", "style": "ノーマル"},
    {"id": 30, "name": "満別花丸",     "style": "ノーマル"},
    {"id": 37, "name": "小夜/SAYO",    "style": "ノーマル"},
    {"id": 38, "name": "ナースロボ＿タイプＴ", "style": "ノーマル"},
    {"id": 39, "name": "†聖騎士 紅桜†", "style": "ノーマル"},
    {"id": 40, "name": "雀松朱司",     "style": "ノーマル"},
    {"id": 41, "name": "麒ヶ島宗麟",   "style": "ノーマル"},
    {"id": 42, "name": "春歌ナナ",     "style": "ノーマル"},
    {"id": 43, "name": "猫使アル",     "style": "ノーマル"},
    {"id": 44, "name": "猫使ビィ",     "style": "ノーマル"},
]


def fetch_speakers_from_engine() -> list[dict] | None:
    """VOICEVOXエンジンからスピーカー一覧を取得する。失敗時はNone"""
    try:
        r = requests.get(f"{VOICEVOX_URL}/speakers", timeout=3)
        r.raise_for_status()
        result = []
        for s in r.json():
            for style in s["styles"]:
                result.append({
                    "id": style["id"],
                    "name": s["name"],
                    "style": style["name"],
                })
        return result
    except Exception:
        return None


def get_speaker_list() -> tuple[list[dict], bool]:
    """
    スピーカー一覧を返す。
    返り値: (speakers, is_live)
      is_live=True: VOICEVOXエンジンから取得
      is_live=False: オフライン一覧から取得
    """
    live = fetch_speakers_from_engine()
    if live:
        return live, True
    return KNOWN_SPEAKERS, False


def find_speaker(name_or_id: str, speakers: list[dict]) -> dict | None:
    """名前（部分一致）またはIDでスピーカーを検索する"""
    # IDで検索
    if name_or_id.isdigit():
        sid = int(name_or_id)
        for s in speakers:
            if s["id"] == sid:
                return s
        return None
    # 名前で検索（部分一致）
    query = name_or_id.lower()
    for s in speakers:
        if query in s["name"].lower() or query in s["style"].lower():
            return s
    return None


def set_speaker_in_env(speaker_id: int, env_path: str = ".env"):
    """
    .envファイルのVOICEVOX_SPEAKERを更新する。
    ファイルが存在しない場合は作成する。
    """
    env_file = Path(env_path)
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        updated = False
        for line in lines:
            if line.startswith("VOICEVOX_SPEAKER="):
                new_lines.append(f"VOICEVOX_SPEAKER={speaker_id}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"VOICEVOX_SPEAKER={speaker_id}")
        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        env_file.write_text(f"VOICEVOX_SPEAKER={speaker_id}\n", encoding="utf-8")


def interactive_select(env_path: str = ".env") -> int:
    """
    対話的にスピーカーを選択して.envに保存する。
    返り値: 選択したスピーカーID
    """
    speakers, is_live = get_speaker_list()

    print()
    if is_live:
        print("✅ VOICEVOXエンジンに接続 — リアルタイムスピーカー一覧")
    else:
        print("⚠️  VOICEVOXエンジン未起動 — オフライン一覧を表示（IDは概算）")

    print()
    print(f"{'ID':>4}  {'キャラクター':<18} {'スタイル'}")
    print("-" * 44)
    for s in speakers:
        print(f"  {s['id']:>3}  {s['name']:<18} {s['style']}")

    print()
    current_id = int(os.getenv("VOICEVOX_SPEAKER", "3"))
    current = find_speaker(str(current_id), speakers)
    current_label = f"{current['name']}（{current['style']}）" if current else f"ID={current_id}"
    print(f"現在の設定: {current_label}")
    print()

    while True:
        raw = input("スピーカーIDまたはキャラクター名を入力 (Enterでキャンセル): ").strip()
        if not raw:
            print("キャンセルしました。")
            return current_id

        speaker = find_speaker(raw, speakers)
        if speaker is None:
            print(f"  ❌ '{raw}' が見つかりません。IDか名前を確認してください。")
            continue

        print(f"  ✅ 選択: ID={speaker['id']} {speaker['name']}（{speaker['style']}）")

        if is_live:
            # 試聴オプション
            preview = input("  試聴しますか？ (y/N): ").strip().lower()
            if preview == "y":
                _preview_speaker(speaker["id"])

        confirm = input(f"  .envに保存しますか？ (Y/n): ").strip().lower()
        if confirm != "n":
            set_speaker_in_env(speaker["id"], env_path)
            print(f"  💾 .env に VOICEVOX_SPEAKER={speaker['id']} を保存しました")
            return speaker["id"]


def _preview_speaker(speaker_id: int, text: str = "こんにちは。私がナレーターを担当します。よろしくお願いします。"):
    """スピーカーを試聴する"""
    import tempfile
    import subprocess
    try:
        r = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker_id},
            timeout=10
        )
        r.raise_for_status()
        query = r.json()
        wav_r = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker_id},
            json=query,
            timeout=30
        )
        wav_r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_r.content)
            tmp_path = f.name
        # 再生（aplayまたはffplay）
        for player in ["aplay", "ffplay -autoexit -nodisp"]:
            try:
                cmd = player.split() + [tmp_path]
                subprocess.run(cmd, check=True, capture_output=True)
                break
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        os.unlink(tmp_path)
        print("  試聴完了")
    except Exception as e:
        print(f"  試聴失敗: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VOICEVOXスピーカーを選択して.envに保存する")
    parser.add_argument("--list", action="store_true", help="一覧表示のみ")
    parser.add_argument("--set", metavar="ID_OR_NAME", help="IDまたは名前で直接設定")
    args = parser.parse_args()

    if args.list:
        speakers, is_live = get_speaker_list()
        label = "（VOICEVOX接続中）" if is_live else "（オフライン一覧）"
        print(f"\nVOICEVOXスピーカー一覧 {label}\n")
        print(f"{'ID':>4}  {'キャラクター':<18} {'スタイル'}")
        print("-" * 44)
        for s in speakers:
            print(f"  {s['id']:>3}  {s['name']:<18} {s['style']}")
    elif args.set:
        speakers, _ = get_speaker_list()
        s = find_speaker(args.set, speakers)
        if s is None:
            print(f"❌ '{args.set}' が見つかりません")
        else:
            set_speaker_in_env(s["id"])
            print(f"✅ VOICEVOX_SPEAKER={s['id']} ({s['name']} / {s['style']}) を.envに保存しました")
    else:
        interactive_select()
