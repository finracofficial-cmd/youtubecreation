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
    VOICEVOX_SPEAKER, VOICEVOX_SPEED,
)


def _resolve_speaker(speaker_arg: str | None) -> int:
    """
    --speaker の引数（IDまたは名前）を解決してIDを返す。
    Noneの場合は.envのVOICEVOX_SPEAKERを使う。
    """
    if speaker_arg is None:
        return VOICEVOX_SPEAKER

    from speaker import get_speaker_list, find_speaker
    speakers, _ = get_speaker_list()
    s = find_speaker(speaker_arg, speakers)
    if s is None:
        print(f"❌ スピーカー '{speaker_arg}' が見つかりません")
        print("   python main.py --list-speakers で一覧を確認してください")
        sys.exit(1)
    print(f"  スピーカー: ID={s['id']} {s['name']}（{s['style']}）")
    return s["id"]


def run_pipeline(script_path: str, output_name: str | None = None,
                 use_solid_bg: bool = False, bg_query_override: str | None = None,
                 dry_run: bool = False, speaker_id: int | None = None):
    """動画生成パイプライン本体"""
    from generate_script import parse_chapter_script

    script_path = Path(script_path)
    if not script_path.exists():
        print(f"❌ 台本ファイルが見つかりません: {script_path}")
        sys.exit(1)

    if output_name is None:
        output_name = script_path.stem

    effective_speaker = speaker_id if speaker_id is not None else VOICEVOX_SPEAKER

    temp_dir = Path(TEMP_DIR) / output_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_output = output_dir / f"{output_name}.mp4"

    print(f"\n=== 台本解析: {script_path} ===")
    lines, meta = parse_chapter_script(str(script_path))
    title = meta.get("title", output_name)
    bg_query = bg_query_override or meta.get("background", "military ocean warship")
    nonempty_lines = [l for l in lines if l.strip()]

    # スピーカー情報を表示
    from speaker import get_speaker_list, find_speaker
    speakers, is_live = get_speaker_list()
    sp = find_speaker(str(effective_speaker), speakers)
    sp_label = f"{sp['name']}（{sp['style']}）" if sp else f"ID={effective_speaker}"
    src_label = "VOICEVOX接続" if is_live else "オフライン一覧"

    print(f"  タイトル  : {title}")
    print(f"  字幕行数  : {len(nonempty_lines)} 行")
    print(f"  背景KW    : {bg_query}")
    print(f"  スピーカー: ID={effective_speaker} {sp_label}  [{src_label}]")

    if dry_run:
        print("\n[DRY RUN] 台本解析のみ実行しました。")
        for i, l in enumerate(nonempty_lines[:10]):
            print(f"  {i+1:3d}: {l[:60]}")
        if len(nonempty_lines) > 10:
            print(f"  ... 以下 {len(nonempty_lines)-10} 行")
        return

    # ── Step 1: VOICEVOX音声合成 ──────────────────────────────────
    print(f"\n=== Step 1: VOICEVOX音声合成 (ID={effective_speaker} / {len(lines)}行) ===")
    try:
        audio_results = voicevox.synthesize_batch(
            lines, str(temp_dir / "audio"),
            speaker=effective_speaker, speed=VOICEVOX_SPEED
        )
    except RuntimeError as e:
        print(f"❌ VOICEVOX接続失敗: {e}")
        print("  VOICEVOXエンジンを起動してから再実行してください")
        print("  → https://voicevox.hiroshiba.jp/")
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

    # ── Step 5: 最終合成 ──────────────────────────────────────────
    print("\n=== Step 5: 動画合成（背景＋音声＋字幕） ===")
    vid.assemble(looped_bg_path, concat_audio_path, ass_path,
                 str(final_output), total_duration)

    size_mb = final_output.stat().st_size / 1024 / 1024
    print(f"\n✅ 完成: {final_output}")
    print(f"   長さ: {total_duration/60:.1f}分 / サイズ: {size_mb:.1f}MB")
    return str(final_output)


def cmd_generate_and_run(topic: str, context: str, output_name: str | None,
                         use_solid_bg: bool, bg_query_override: str | None,
                         speaker_id: int | None):
    """台本生成→動画生成まで全自動実行"""
    from generate_script import generate, save_script

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY が設定されていません（.envに追加してください）")
        sys.exit(1)

    print(f"\n=== 台本生成: '{topic}' ===")
    script_text = generate(topic, context)
    script_path = save_script(script_text, output_name)
    print(f"  → 台本保存: {script_path}")
    print(f"  → 文字数: {len(script_text):,}")

    run_pipeline(script_path, output_name, use_solid_bg, bg_query_override,
                 speaker_id=speaker_id)


def main():
    parser = argparse.ArgumentParser(
        description="YouTube動画自動生成パイプライン（軍事系ニュース解説スタイル）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  # ① スピーカーを対話選択して.envに保存（まず最初に実行）
  python main.py --select-speaker

  # ② テーマから全自動生成（台本→音声→動画）
  python main.py --topic "中国の空母戦力と日本の対応策"

  # ③ 既存台本から動画生成
  python main.py scripts/sample_military.txt

  # スピーカーをその場で指定（IDまたは名前）
  python main.py scripts/sample_military.txt --speaker 11
  python main.py --topic "イージス艦" --speaker ずんだもん

  # 台本のみ生成
  python generate_script.py "イージス艦の迎撃能力"

  # テスト（黒背景・dry-run）
  python main.py scripts/sample_military.txt --solid-bg --dry-run

  # スピーカー一覧
  python main.py --list-speakers
  python speaker.py --list
        """
    )

    # モード選択
    group = parser.add_mutually_exclusive_group()
    group.add_argument("script", nargs="?", help="既存の台本ファイルパス")
    group.add_argument("--topic", metavar="TOPIC",
                       help="動画テーマ（Claude APIで台本を自動生成）")
    group.add_argument("--select-speaker", action="store_true",
                       help="スピーカーを対話選択して.envに保存")
    group.add_argument("--list-speakers", action="store_true",
                       help="VOICEVOXスピーカー一覧を表示")

    # オプション
    parser.add_argument("--speaker", metavar="ID_OR_NAME",
                        help="使用するスピーカーのIDまたは名前（例: 3, ずんだもん, 玄野武宏）")
    parser.add_argument("-o", "--output", help="出力ファイル名（拡張子なし）")
    parser.add_argument("--context", default="",
                        help="台本生成の追加コンテキスト（--topicと併用）")
    parser.add_argument("--solid-bg", action="store_true",
                        help="Pexels不使用・黒背景（テスト用）")
    parser.add_argument("--bg", metavar="KEYWORD",
                        help="Pexels検索キーワード上書き（英語）")
    parser.add_argument("--dry-run", action="store_true",
                        help="台本解析のみ（音声・動画生成をスキップ）")

    args = parser.parse_args()

    # ── スピーカー関連コマンド ────────────────────────────────────
    if args.select_speaker:
        from speaker import interactive_select
        interactive_select()
        return

    if args.list_speakers:
        from speaker import get_speaker_list
        speakers, is_live = get_speaker_list()
        label = "（VOICEVOX接続中）" if is_live else "（オフライン一覧 / IDは概算）"
        print(f"\nVOICEVOXスピーカー一覧 {label}\n")
        print(f"{'ID':>4}  {'キャラクター':<18} {'スタイル'}")
        print("-" * 44)
        for s in speakers:
            print(f"  {s['id']:>3}  {s['name']:<18} {s['style']}")
        current = int(os.getenv("VOICEVOX_SPEAKER", "3"))
        print(f"\n現在の設定 (.env): VOICEVOX_SPEAKER={current}")
        return

    # ── スピーカーID解決 ─────────────────────────────────────────
    speaker_id = _resolve_speaker(args.speaker)

    # ── メインパイプライン ────────────────────────────────────────
    if args.topic:
        cmd_generate_and_run(
            args.topic, args.context, args.output,
            args.solid_bg, args.bg, speaker_id
        )
    elif args.script:
        run_pipeline(args.script, args.output, args.solid_bg, args.bg,
                     args.dry_run, speaker_id)
    else:
        scripts = sorted(Path(SCRIPTS_DIR).glob("*.txt"))
        if not scripts:
            print(f"❌ 台本ファイルが見つかりません: {SCRIPTS_DIR}/")
            print("   python main.py --topic 'テーマ' で台本から自動生成できます")
            sys.exit(1)
        print(f"  台本自動選択: {scripts[0]}")
        run_pipeline(str(scripts[0]), args.output, args.solid_bg, args.bg,
                     args.dry_run, speaker_id)


if __name__ == "__main__":
    main()
