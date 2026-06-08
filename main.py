#!/usr/bin/env python3
"""
YouTube動画自動生成パイプライン
ニュース解説系・フル背景動画＋字幕スタイル
"""
import argparse
import shutil
import sys
from pathlib import Path

import voicevox
import pexels
import subtitle
import video as vid
from config import (
    OUTPUT_DIR, TEMP_DIR, SCRIPTS_DIR,
    PEXELS_API_KEY, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS
)


def load_script(script_path: str) -> tuple[list[str], dict]:
    """
    台本ファイルを読み込む。
    形式:
      # メタデータ行（先頭 # で始まる）
      ## background: city night  ← Pexels検索キーワード
      ## title: 動画タイトル
      ---
      ナレーション行1
      ナレーション行2
      ...
    """
    content = Path(script_path).read_text(encoding="utf-8")
    meta = {}
    lines = []

    in_script = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            # メタデータ: ## key: value
            kv = stripped[2:].strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
                meta[k.strip()] = v.strip()
        elif stripped == "---":
            in_script = True
        elif in_script:
            lines.append(stripped)

    return lines, meta


def run(script_path: str, output_name: str | None = None,
        use_solid_bg: bool = False, bg_query_override: str | None = None):
    """メインパイプライン実行"""
    script_path = Path(script_path)
    if not script_path.exists():
        print(f"❌ 台本ファイルが見つかりません: {script_path}")
        sys.exit(1)

    # 出力ファイル名
    if output_name is None:
        output_name = script_path.stem

    temp_dir = Path(TEMP_DIR) / output_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_output = output_dir / f"{output_name}.mp4"

    print(f"\n=== 台本読み込み: {script_path} ===")
    lines, meta = load_script(str(script_path))
    title = meta.get("title", output_name)
    bg_query = bg_query_override or meta.get("background", "nature landscape")
    print(f"  タイトル: {title}")
    print(f"  行数: {len(lines)}")
    print(f"  背景キーワード: {bg_query}")

    # ── Step 1: VOICEVOX音声合成 ──────────────────────────────────
    print(f"\n=== Step 1: VOICEVOX音声合成 ({len(lines)}行) ===")
    try:
        audio_results = voicevox.synthesize_batch(
            lines, str(temp_dir / "audio")
        )
    except RuntimeError as e:
        print(f"❌ VOICEVOX接続失敗: {e}")
        print("  VOICEVOXエンジンが起動しているか確認してください")
        print("  起動コマンド: ./run.sh (または VoiceVox.exeを起動)")
        sys.exit(1)

    wav_files = [r[0] for r in audio_results]
    durations = [r[1] for r in audio_results]
    total_duration = sum(durations)
    print(f"  合計音声長: {total_duration:.1f}秒 ({total_duration/60:.1f}分)")

    # ── Step 2: 音声ファイル連結 ──────────────────────────────────
    print("\n=== Step 2: 音声ファイル連結 ===")
    concat_audio_path = str(temp_dir / "narration.wav")
    vid.concat_audio(wav_files, concat_audio_path)
    print(f"  → {concat_audio_path}")

    # ── Step 3: 字幕ファイル生成 ──────────────────────────────────
    print("\n=== Step 3: 字幕ファイル生成 ===")
    ass_path = str(temp_dir / "subtitle.ass")
    subtitle.generate_ass(lines, durations, ass_path)
    srt_path = str(temp_dir / "subtitle.srt")
    subtitle.generate_srt(lines, durations, srt_path)
    print(f"  → {ass_path}")
    print(f"  → {srt_path}")

    # ── Step 4: 背景動画取得 ──────────────────────────────────────
    print(f"\n=== Step 4: 背景動画取得 ('{bg_query}') ===")
    raw_bg_path = str(temp_dir / "background_raw.mp4")
    looped_bg_path = str(temp_dir / "background.mp4")

    if use_solid_bg or not PEXELS_API_KEY:
        if not PEXELS_API_KEY:
            print("  ⚠️  PEXELS_API_KEY未設定 → 黒背景で代替")
        pexels.generate_solid_background(
            looped_bg_path, total_duration,
            width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fps=VIDEO_FPS
        )
    else:
        pexels.fetch_background(bg_query, raw_bg_path)
        print(f"  背景動画をループ処理中（{total_duration:.1f}秒）...")
        vid.loop_video_to_duration(raw_bg_path, looped_bg_path, total_duration)
    print(f"  → {looped_bg_path}")

    # ── Step 5: 最終合成 ──────────────────────────────────────────
    print("\n=== Step 5: 動画合成（背景＋音声＋字幕） ===")
    vid.assemble(looped_bg_path, concat_audio_path, ass_path,
                 str(final_output), total_duration)
    print(f"\n✅ 完成: {final_output}")
    print(f"   サイズ: {final_output.stat().st_size / 1024 / 1024:.1f} MB")

    return str(final_output)


def main():
    parser = argparse.ArgumentParser(
        description="YouTube動画自動生成パイプライン（VOICEVOX＋Pexels＋FFmpeg）"
    )
    parser.add_argument("script", nargs="?",
                        help="台本ファイルのパス（省略時はscripts/内のファイルを自動検索）")
    parser.add_argument("-o", "--output", help="出力ファイル名（拡張子なし）")
    parser.add_argument("--solid-bg", action="store_true",
                        help="Pexels不使用・黒背景で生成（テスト用）")
    parser.add_argument("--bg", help="Pexels検索キーワードを上書き")
    parser.add_argument("--list-speakers", action="store_true",
                        help="VOICEVOXのスピーカー一覧を表示")
    args = parser.parse_args()

    if args.list_speakers:
        speakers = voicevox.get_speakers()
        for s in speakers:
            for style in s["styles"]:
                print(f"  ID: {style['id']:3d} | {s['name']} ({style['name']})")
        return

    # 台本ファイルの特定
    script_path = args.script
    if script_path is None:
        scripts = list(Path(SCRIPTS_DIR).glob("*.txt"))
        if not scripts:
            print(f"❌ {SCRIPTS_DIR}/ に台本ファイルが見つかりません")
            print("   使い方: python main.py <台本ファイル.txt>")
            sys.exit(1)
        script_path = str(scripts[0])
        print(f"  台本自動選択: {script_path}")

    run(script_path, args.output, use_solid_bg=args.solid_bg,
        bg_query_override=args.bg)


if __name__ == "__main__":
    main()
