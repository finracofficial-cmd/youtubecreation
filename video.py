"""FFmpegを使った動画合成モジュール"""
import subprocess
from pathlib import Path
from config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS


def _run(cmd: list[str]) -> None:
    """FFmpegコマンドを実行し、失敗時はstderrを含めてエラーを出す"""
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"FFmpeg 失敗 (exit {result.returncode}):\n"
            f"  コマンド: {' '.join(cmd)}\n"
            f"  stderr: {stderr[-2000:]}"  # 末尾2000文字
        )


def concat_audio(wav_files: list[str], output_path: str) -> str:
    """複数のWAVファイルを連結して1つのWAVにする"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.replace(".wav", "_list.txt")
    with open(list_file, "w") as f:
        for wav in wav_files:
            abs_path = str(Path(wav).resolve())
            f.write(f"file '{abs_path}'\n")

    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-ar", "44100", "-ac", "1",  # 全ファイルを同一フォーマットに正規化
        output_path
    ])
    return output_path


def loop_video_to_duration(input_video: str, output_path: str, duration: float) -> str:
    """
    背景動画を指定秒数になるようにループさせる。
    動画が短い場合は繰り返し、長い場合はカットする。
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", input_video,
        "-t", str(duration),
        "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        output_path
    ])
    return output_path


def assemble(background_video: str, audio_file: str, subtitle_file: str,
             output_path: str, duration: float) -> str:
    """
    背景動画 + 音声 + 字幕を合成して最終MP4を生成する。
    subtitle_file: .ass ファイルパス
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 字幕フィルタを設定（FFmpegフィルタグラフ用パスエスケープ）
    abs_sub = str(Path(subtitle_file).resolve())
    # コロン・バックスラッシュ・シングルクォートをエスケープ
    esc_sub = abs_sub.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    if subtitle_file.endswith(".ass"):
        sub_filter = f"ass={esc_sub}"
    else:
        from config import (
            SUBTITLE_FONT, SUBTITLE_FONT_SIZE, SUBTITLE_MARGIN_V,
            SUBTITLE_OUTLINE
        )
        style = (
            f"FontName={SUBTITLE_FONT},"
            f"FontSize={SUBTITLE_FONT_SIZE},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=1,"
            f"Outline={SUBTITLE_OUTLINE},"
            f"Shadow=0,"
            f"Alignment=2,"
            f"MarginV={SUBTITLE_MARGIN_V}"
        )
        sub_filter = f"subtitles={esc_sub}:force_style='{style}'"

    _run([
        "ffmpeg", "-y",
        "-i", background_video,
        "-i", audio_file,
        "-t", str(duration),
        "-vf", sub_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path
    ])
    return output_path


def create_varied_background(video_paths: list[str], output_path: str,
                             total_duration: float, clip_duration: float = 10.0) -> str:
    """
    複数の背景動画クリップを各最大clip_duration秒にトリムしてランダム順で連結する。
    クリップ数が足りない場合のみループで補完する。
    """
    import math
    import random
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(output_path).parent / "_clips"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 各クリップをトリム＆スケール
    trimmed = []
    for i, vp in enumerate(video_paths):
        out = str(temp_dir / f"trimmed_{i:02d}.mp4")
        _run([
            "ffmpeg", "-y",
            "-i", vp,
            "-t", str(clip_duration),
            "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
            "-r", str(VIDEO_FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-an",
            out
        ])
        trimmed.append(out)

    random.shuffle(trimmed)  # 毎回ランダムな順番で並べる

    clips_total = len(trimmed) * clip_duration
    print(f"  クリップ合計: {len(trimmed)}本 × {clip_duration}秒 = {clips_total:.0f}秒 / 必要: {total_duration:.0f}秒")

    # 連結リストを作成: クリップが足りない場合はシャッフルしながら繰り返す
    needed = math.ceil(total_duration / clip_duration)
    entries = []
    while len(entries) < needed:
        pool = trimmed[:]
        random.shuffle(pool)
        entries.extend(pool)
    entries = entries[:needed]

    list_file = str(temp_dir / "concat_list.txt")
    with open(list_file, "w") as f:
        for t in entries:
            f.write(f"file '{Path(t).resolve()}'\n")

    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-t", str(total_duration),
        "-c", "copy",
        output_path
    ])
    return output_path


def image_to_clip(image_path: str, output_path: str, duration: float = 5.0) -> str:
    """
    静止画にケン・バーンズ風アニメをかけて動画クリップにする。
    zoompanの代わりにscale+cropを使い高速化（10〜20倍速）。
    """
    import random
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    # 1.3倍に拡大してパン・ズームの余白を確保
    sw, sh = int(w * 1.3), int(h * 1.3)

    # パターンをランダム選択（開始crop位置 → 終了crop位置）
    patterns = [
        # 左上→右下（ズームイン風）
        (0, 0, sw - w, sh - h),
        # 右下→左上
        (sw - w, sh - h, 0, 0),
        # 左→右（横パン）
        (0, (sh - h) // 2, sw - w, (sh - h) // 2),
        # 右→左
        (sw - w, (sh - h) // 2, 0, (sh - h) // 2),
        # 上→下（縦パン）
        ((sw - w) // 2, 0, (sw - w) // 2, sh - h),
    ]
    x1, y1, x2, y2 = random.choice(patterns)

    vf = (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={sw}:{sh},"
        f"crop=w={w}:h={h}:"
        f"x='{x1}+({x2}-{x1})*t/{duration}':"
        f"y='{y1}+({y2}-{y1})*t/{duration}',"
        f"setsar=1"
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        output_path
    ])
    return output_path


def create_mixed_background(video_paths: list[str], image_paths: list[str],
                             output_path: str, total_duration: float,
                             clip_duration: float = 10.0,
                             image_clip_duration: float = 5.0) -> str:
    """
    背景動画クリップと画像アニメクリップをランダムに交互配置して連結する。
    """
    import math
    import random
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(output_path).parent / "_clips"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 動画クリップをトリム＆スケール
    trimmed_videos = []
    for i, vp in enumerate(video_paths):
        out = str(temp_dir / f"vid_{i:02d}.mp4")
        _run([
            "ffmpeg", "-y", "-i", vp,
            "-t", str(clip_duration),
            "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
            "-r", str(VIDEO_FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
            out
        ])
        trimmed_videos.append(out)

    # 画像クリップをアニメ化
    animated_images = []
    for i, ip in enumerate(image_paths):
        out = str(temp_dir / f"img_{i:02d}.mp4")
        try:
            image_to_clip(ip, out, duration=image_clip_duration)
            animated_images.append(out)
            print(f"  画像アニメ [{i+1}/{len(image_paths)}] 完了")
        except Exception as e:
            print(f"  画像アニメ スキップ: {e}")

    # 動画と画像クリップをシャッフルして交互に配置
    random.shuffle(trimmed_videos)
    random.shuffle(animated_images)

    # 交互配置: video, image, video, image, ...
    all_clips = []
    vi, ii = 0, 0
    while vi < len(trimmed_videos) or ii < len(animated_images):
        if vi < len(trimmed_videos):
            all_clips.append(trimmed_videos[vi]); vi += 1
        if ii < len(animated_images):
            all_clips.append(animated_images[ii]); ii += 1

    if not all_clips:
        raise ValueError("クリップが1本もありません")

    # 必要な秒数になるまでリストを繰り返す（クリップ数 × 各クリップ秒数 ≥ total_duration）
    avg_clip_sec = (clip_duration * len(trimmed_videos) + image_clip_duration * len(animated_images)) / max(len(all_clips), 1)
    needed = math.ceil(total_duration / avg_clip_sec) + 2
    entries = []
    while len(entries) < needed:
        pool = all_clips[:]
        random.shuffle(pool)
        entries.extend(pool)
    entries = entries[:needed]

    list_file = str(temp_dir / "mixed_list.txt")
    with open(list_file, "w") as f:
        for t in entries:
            f.write(f"file '{Path(t).resolve()}'\n")

    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-t", str(total_duration),
        "-c", "copy",
        output_path
    ])
    return output_path


def overlay_announcer(background_video: str, announcer_video: str,
                      output_path: str, total_duration: float,
                      scale_height: int = 800) -> str:
    """
    アナウンサー動画（背景透過済みまたはグリーンバック）を
    背景動画の中央下部にループ合成する。
    アルファチャンネルがあればそのまま使い、なければcolorkey（黒抜き）を試みる。
    """
    import subprocess as _sp
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # アルファチャンネルの有無を確認
    probe = _sp.run([
        "ffprobe", "-v", "quiet", "-select_streams", "v:0",
        "-show_entries", "stream=pix_fmt",
        "-of", "csv=p=0", announcer_video
    ], capture_output=True, text=True)
    pix_fmt = probe.stdout.strip()
    has_alpha = "a" in pix_fmt  # yuva420p, rgba など
    print(f"  アナウンサー pix_fmt={pix_fmt} has_alpha={has_alpha}")

    ann_abs = str(Path(announcer_video).resolve())

    # 中央横・縦は下寄せ（字幕より上）
    y_pos = "(H-h)*3/4"
    x_pos = "(W-w)/2"

    if has_alpha:
        # アルファチャンネルで透過合成
        # -stream_loop -1 でインプット段階でループ、filter内でloopは使わない
        filter_complex = (
            f"[0:v]scale=-1:{scale_height}[ann];"
            f"[1:v][ann]overlay={x_pos}:{y_pos}"
        )
        _run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", ann_abs,
            "-i", background_video,
            "-filter_complex", filter_complex,
            "-t", str(total_duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an", output_path
        ])
    else:
        # 黒背景抜き（colorkey）でフォールバック
        filter_complex = (
            f"[0:v]scale=-1:{scale_height},"
            f"colorkey=black:0.25:0.05[ann];"
            f"[1:v][ann]overlay={x_pos}:{y_pos}"
        )
        _run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", ann_abs,
            "-i", background_video,
            "-filter_complex", filter_complex,
            "-t", str(total_duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an", output_path
        ])
    return output_path


def get_video_duration(video_path: str) -> float:
    """動画の長さを取得する"""
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())
