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
    複数の背景動画クリップを各最大clip_duration秒にトリムして連結し、
    total_durationになるまでループした背景動画を生成する。
    """
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

    # 連結リストを作成して1本に
    concat_path = str(temp_dir / "concat_once.mp4")
    list_file = str(temp_dir / "concat_list.txt")
    with open(list_file, "w") as f:
        for t in trimmed:
            f.write(f"file '{Path(t).resolve()}'\n")
    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        concat_path
    ])

    # total_durationになるようループ
    _run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", concat_path,
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
