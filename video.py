"""FFmpegを使った動画合成モジュール"""
import subprocess
from pathlib import Path
from config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS


def concat_audio(wav_files: list[str], output_path: str) -> str:
    """複数のWAVファイルを連結して1つのWAVにする"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.replace(".wav", "_list.txt")
    with open(list_file, "w") as f:
        for wav in wav_files:
            abs_path = str(Path(wav).resolve())
            f.write(f"file '{abs_path}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ], check=True, capture_output=True)
    return output_path


def loop_video_to_duration(input_video: str, output_path: str, duration: float) -> str:
    """
    背景動画を指定秒数になるようにループさせる。
    動画が短い場合は繰り返し、長い場合はカットする。
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", input_video,
        "-t", str(duration),
        "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an",
        output_path
    ], check=True, capture_output=True)
    return output_path


def assemble(background_video: str, audio_file: str, subtitle_file: str,
             output_path: str, duration: float) -> str:
    """
    背景動画 + 音声 + 字幕を合成して最終MP4を生成する。
    subtitle_file: .srt または .ass ファイルパス
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 字幕フィルタを設定
    abs_sub = str(Path(subtitle_file).resolve())
    if subtitle_file.endswith(".ass"):
        sub_filter = f"ass={abs_sub}"
    else:
        # SRTはforce_styleでスタイル指定
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
        # パスのコロン・バックスラッシュをエスケープ（Linux不要だが念のため）
        safe_path = abs_sub.replace("\\", "/").replace(":", "\\:")
        sub_filter = f"subtitles={safe_path}:force_style='{style}'"

    subprocess.run([
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
    ], check=True, capture_output=True)
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
