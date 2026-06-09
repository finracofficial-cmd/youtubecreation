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
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
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
    静止画にランダムなケン・バーンズ効果（ズーム・パン）をかけて動画クリップにする。
    """
    import random
    d = int(duration * VIDEO_FPS)  # フレーム数
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT

    # 事前に出力の2倍解像度へ拡大＆クロップ。
    #  - 低解像度画像でも滑らかにズーム/パンできる（ジッター防止）
    #  - 出力アスペクト比にぴったり合わせて余白が出ない
    pre = (
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={w*2}:{h*2},setsar=1"
    )

    # ランダムにアニメスタイルを選ぶ
    style = random.choice([
        # ゆっくりズームイン
        f"{pre},zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={VIDEO_FPS}",
        # ゆっくりズームアウト
        f"{pre},zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={VIDEO_FPS}",
        # 左から右へパン
        f"{pre},zoompan=z=1.2:x='iw/2-(iw/zoom/2)+((iw-(iw/zoom))/2)*on/{d}':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={VIDEO_FPS}",
        # 右から左へパン
        f"{pre},zoompan=z=1.2:x='iw/2-(iw/zoom/2)+((iw-(iw/zoom))/2)*(1-on/{d})':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={VIDEO_FPS}",
    ])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-vf", style,
        "-t", str(duration),
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
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-an",
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

    # 必要な秒数になるまでリストを繰り返す
    needed = math.ceil(total_duration / min(clip_duration, image_clip_duration))
    entries = []
    while len(entries) < needed:
        pool = all_clips[:]
        random.shuffle(pool)
        entries.extend(pool)
    entries = entries[:needed * 2]  # 余裕を持って用意

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


def get_video_duration(video_path: str) -> float:
    """動画の長さを取得する"""
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())
