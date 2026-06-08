"""字幕（SRT/ASS）生成モジュール"""
from pathlib import Path
from config import (
    SUBTITLE_FONT, SUBTITLE_FONT_SIZE, SUBTITLE_COLOR,
    SUBTITLE_OUTLINE_COLOR, SUBTITLE_OUTLINE, SUBTITLE_MARGIN_V
)


def seconds_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def generate_srt(lines: list[str], durations: list[float], output_path: str,
                 gap: float = 0.05) -> str:
    """
    各行とその音声長からSRTファイルを生成する。
    gap: 字幕間の隙間（秒）
    """
    srt = ""
    t = 0.0
    idx = 1
    for line, dur in zip(lines, durations):
        if not line.strip():
            t += dur
            continue
        start = seconds_to_srt_time(t)
        end = seconds_to_srt_time(t + dur - gap)
        srt += f"{idx}\n{start} --> {end}\n{line}\n\n"
        t += dur
        idx += 1

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(srt, encoding="utf-8")
    return output_path


def generate_ass(lines: list[str], durations: list[float], output_path: str,
                 gap: float = 0.05) -> str:
    """
    ASSファイルを生成する（SRTより高機能なスタイリングが可能）。
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{SUBTITLE_FONT},{SUBTITLE_FONT_SIZE},{SUBTITLE_COLOR},&H000000FF,{SUBTITLE_OUTLINE_COLOR},&H00000000,-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},0,2,10,10,{SUBTITLE_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = ""
    t = 0.0
    for line, dur in zip(lines, durations):
        if not line.strip():
            t += dur
            continue
        start = seconds_to_ass_time(t)
        end = seconds_to_ass_time(t + dur - gap)
        events += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{line}\n"
        t += dur

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(header + events, encoding="utf-8")
    return output_path
