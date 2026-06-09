import os
from dotenv import load_dotenv

load_dotenv()

# AivisSpeech Engine設定
TTS_ENGINE_URL    = os.getenv("TTS_ENGINE_URL", "http://localhost:10101")
TTS_SPEAKER_NAME  = os.getenv("TTS_SPEAKER_NAME", "阿井田 茂")
TTS_STYLE_NAME    = os.getenv("TTS_STYLE_NAME", "Calm")
TTS_SPEED         = float(os.getenv("TTS_SPEED", "1.0"))

# 後方互換
TTS_SPEAKER = os.getenv("TTS_SPEAKER", TTS_SPEAKER_NAME)
TTS_STYLE   = os.getenv("TTS_STYLE", TTS_STYLE_NAME)
TTS_DEVICE  = os.getenv("TTS_DEVICE", "cpu")

# Pexels API
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# Serper.dev（Google画像検索）
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

# 動画設定
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))

# 字幕スタイル（FFmpeg ASS形式）
SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "Noto Sans CJK JP")
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", "52"))
SUBTITLE_COLOR = os.getenv("SUBTITLE_COLOR", "&H00FFFFFF")   # 白
SUBTITLE_OUTLINE_COLOR = os.getenv("SUBTITLE_OUTLINE_COLOR", "&H00000000")  # 黒縁
SUBTITLE_OUTLINE = int(os.getenv("SUBTITLE_OUTLINE", "3"))
SUBTITLE_MARGIN_V = int(os.getenv("SUBTITLE_MARGIN_V", "60"))

# 出力ディレクトリ
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
TEMP_DIR = os.getenv("TEMP_DIR", "temp")
SCRIPTS_DIR = os.getenv("SCRIPTS_DIR", "scripts")
