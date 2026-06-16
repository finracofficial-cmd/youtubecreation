#!/usr/bin/env python3
"""
YouTube動画自動生成パイプライン
軍事系ニュース解説・フル背景動画＋字幕スタイル

使い方:
  # スピーカーを対話選択して.envに保存
  python main.py --select-speaker

  # テーマから台本生成→動画生成まで全自動
  python main.py --topic "中国の空母戦力と日本の対応策"

  # 既存の台本ファイルから動画生成
  python main.py scripts/my_script.txt

  # スピーカーをその場で指定（--speaker 3 または --speaker ずんだもん）
  python main.py scripts/my_script.txt --speaker 11
"""
import argparse
import os
import sys
from pathlib import Path

import voicevox
import pexels
import subtitle
import video as vid
from config import (
    OUTPUT_DIR, TEMP_DIR, SCRIPTS_DIR,
    PEXELS_API_KEY, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    TTS_SPEAKER_NAME, TTS_SPEED,
)



def run_pipeline(script_path: str, output_name: str | None = None,
                 use_solid_bg: bool = False, bg_query_override: str | None = None,
                 dry_run: bool = False, speaker_id: str | None = None):
    """動画生成パイプライン本体"""
    from generate_script import parse_chapter_script

    script_path = Path(script_path)
    if not script_path.exists():
        print(f"❌ 台本ファイルが見つかりません: {script_path}")
        sys.exit(1)

    if output_name is None:
        output_name = script_path.stem

    effective_speaker = speaker_id if speaker_id is not None else TTS_SPEAKER_NAME

    temp_dir = Path(TEMP_DIR) / output_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_output = output_dir / f"{output_name}.mp4"

    print(f"\n=== 台本解析: {script_path} ===")
    lines, meta = parse_chapter_script(str(script_path))
    title = meta.get("title", output_name)
    bg_query = bg_query_override or meta.get("background", "military japan defense")
    nonempty_lines = [l for l in lines if l.strip()]

    print(f"  タイトル  : {title}")
    print(f"  字幕行数  : {len(nonempty_lines)} 行")
    print(f"  背景KW    : {bg_query}")
    print(f"  スピーカー: {effective_speaker}")

    if dry_run:
        print("\n[DRY RUN] 台本解析のみ実行しました。")
        for i, l in enumerate(nonempty_lines[:10]):
            print(f"  {i+1:3d}: {l[:60]}")
        if len(nonempty_lines) > 10:
            print(f"  ... 以下 {len(nonempty_lines)-10} 行")
        return

    # ── Step 1: TTS音声合成 ───────────────────────────────────────
    print(f"\n=== Step 1: TTS音声合成 ({effective_speaker} / {len(lines)}行) ===")
    try:
        audio_results = voicevox.synthesize_batch(
            lines, str(temp_dir / "audio"),
            speaker=effective_speaker, speed=TTS_SPEED
        )
    except RuntimeError as e:
        print(f"❌ TTS失敗: {e}")
        sys.exit(1)

    wav_files = [r[0] for r in audio_results]
    durations = [r[1] for r in audio_results]
    total_duration = sum(durations)
    print(f"  合計音声長: {total_duration:.1f}秒 ({total_duration/60:.1f}分)")

    # ── Step 2: 音声ファイル連結 ──────────────────────────────────
    print("\n=== Step 2: 音声ファイル連結 ===")
    concat_audio_path = str(temp_dir / "narration.wav")
    vid.concat_audio(wav_files, concat_audio_path)

    # ── Step 3: 字幕ファイル生成 ──────────────────────────────────
    print("\n=== Step 3: 字幕ファイル生成 ===")
    ass_path = str(temp_dir / "subtitle.ass")
    subtitle.generate_ass(lines, durations, ass_path)
    srt_path = str(temp_dir / "subtitle.srt")
    subtitle.generate_srt(lines, durations, srt_path)
    print(f"  → {ass_path}")

    # ── Step 4: 背景動画取得 ──────────────────────────────────────
    print(f"\n=== Step 4: 背景動画取得 ('{bg_query}') ===")
    looped_bg_path = str(temp_dir / "background.mp4")

    if use_solid_bg or not PEXELS_API_KEY:
        if not PEXELS_API_KEY:
            print("  ⚠️  PEXELS_API_KEY未設定 → 黒背景で代替")
        pexels.generate_solid_background(
            looped_bg_path, total_duration,
            width=VIDEO_WIDTH, height=VIDEO_HEIGHT, fps=VIDEO_FPS
        )
    else:
        import math
        clip_sec = 10.0
        image_sec = 5.0
        # 動画クリップ: 全体の2/3、画像クリップ: 1/3 を目安に本数計算
        n_video = min(math.ceil(total_duration / clip_sec * 2 / 3), 40)
        n_image = min(math.ceil(total_duration / image_sec * 1 / 3), 20)

        clips_dir = str(temp_dir / "bg_clips")
        images_dir = str(temp_dir / "bg_images")

        # 台本内容からPexels検索キーワードをClaudeが抽出
        from image_search import extract_video_queries, fetch_script_images
        video_queries = extract_video_queries(
            script_path.read_text(encoding="utf-8"), n=8
        )
        # クエリごとに均等本数ダウンロードして混合
        import math as _math
        n_per_vq = max(1, _math.ceil(n_video / len(video_queries)))
        clip_paths = []
        for vq in video_queries:
            if len(clip_paths) >= n_video:
                break
            need = min(n_per_vq, n_video - len(clip_paths))
            vq_dir = str(Path(clips_dir) / vq.replace(" ", "_")[:30])
            print(f"  背景動画「{vq}」を{need}本ダウンロード中...")
            try:
                paths = pexels.fetch_multiple_backgrounds(vq, vq_dir, n=need)
                clip_paths.extend(paths)
            except Exception as e:
                print(f"  スキップ ({vq}): {e}")
        if not clip_paths:
            print("  ⚠️ 台本クエリで動画が取れなかった → フォールバック")
            clip_paths = pexels.fetch_multiple_backgrounds(bg_query, clips_dir, n=n_video)

        # 台本内容からGoogle画像検索（Serper）で高画質画像を取得
        print(f"  台本関連画像をGoogle画像検索で取得中...")
        image_paths = fetch_script_images(
            script_path.read_text(encoding="utf-8"),
            images_dir, n_queries=10, n_per_query=2
        )

        print(f"  動画{len(clip_paths)}本＋画像{len(image_paths)}枚を混合中（合計{total_duration:.1f}秒）...")
        vid.create_mixed_background(
            clip_paths, image_paths, looped_bg_path, total_duration,
            clip_duration=clip_sec, image_clip_duration=image_sec
        )

    # ── Step 5: 最終合成 ──────────────────────────────────────────
    print("\n=== Step 5: 動画合成（背景＋音声＋字幕） ===")
    vid.assemble(looped_bg_path, concat_audio_path, ass_path,
                 str(final_output), total_duration)

    size_mb = final_output.stat().st_size / 1024 / 1024
    print(f"\n✅ 完成: {final_output}")
    print(f"   長さ: {total_duration/60:.1f}分 / サイズ: {size_mb:.1f}MB")
    return str(final_output)



def main():
    parser = argparse.ArgumentParser(description="YouTube動画自動生成パイプライン")
    parser.add_argument("script", nargs="?", help="台本ファイルパス")
    parser.add_argument("-o", "--output", help="出力ファイル名（拡張子なし）")
    parser.add_argument("--solid-bg", action="store_true", help="黒背景（テスト用）")
    parser.add_argument("--bg", metavar="KEYWORD", help="Pexels検索キーワード上書き")
    parser.add_argument("--dry-run", action="store_true", help="台本解析のみ")

    args = parser.parse_args()

    # ── メインパイプライン ────────────────────────────────────────
    if args.script:
        run_pipeline(args.script, args.output, args.solid_bg, args.bg,
                     args.dry_run, None)
    else:
        scripts = sorted(Path(SCRIPTS_DIR).glob("*.txt"))
        if not scripts:
            print(f"❌ 台本ファイルが見つかりません: {SCRIPTS_DIR}/")
            print("   python main.py --topic 'テーマ' で台本から自動生成できます")
            sys.exit(1)
        print(f"  台本自動選択: {scripts[0]}")
        run_pipeline(str(scripts[0]), args.output, args.solid_bg, args.bg,
                     args.dry_run, None)


if __name__ == "__main__":
    main()
