"""Pexels APIを使ったフリー背景動画の取得モジュール"""
import random
import requests
from pathlib import Path
from config import PEXELS_API_KEY


def search_videos(query: str, per_page: int = 10) -> list[dict]:
    """キーワードで動画を検索する"""
    if not PEXELS_API_KEY:
        raise ValueError("PEXELS_API_KEY が設定されていません（.envファイルを確認してください）")

    r = requests.get(
        "https://api.pexels.com/v1/videos/search",
        headers={"Authorization": PEXELS_API_KEY},
        params={
            "query": query,
            "orientation": "landscape",
            "size": "large",
            "per_page": per_page,
        },
        timeout=15
    )
    r.raise_for_status()
    return r.json().get("videos", [])


def get_hd_url(video: dict) -> str | None:
    """動画オブジェクトからHD動画URLを取得する"""
    files = video.get("video_files", [])
    # HD優先、なければSDを選択
    for quality in ("hd", "sd"):
        for f in files:
            if f.get("quality") == quality:
                return f["link"]
    return None


def download_video(url: str, output_path: str) -> str:
    """動画をダウンロードして保存する"""
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


def fetch_background(query: str, output_path: str, prefer_index: int | None = None) -> str:
    """
    キーワードに合う背景動画を検索してダウンロードする。
    prefer_index: Noneの場合はランダム選択
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    videos = search_videos(query, per_page=15)
    if not videos:
        raise ValueError(f"'{query}' に一致する動画が見つかりませんでした")

    if prefer_index is not None:
        video = videos[prefer_index % len(videos)]
    else:
        video = random.choice(videos)

    url = get_hd_url(video)
    if not url:
        raise ValueError("HD動画URLが取得できませんでした")

    print(f"  背景動画: Pexels ID={video['id']} をダウンロード中...")
    return download_video(url, output_path)


# Pexels APIキーなしでも動作するフォールバック（単色背景）
def generate_solid_background(output_path: str, duration: float,
                               color: str = "black",
                               width: int = 1920, height: int = 1080,
                               fps: int = 30) -> str:
    """FFmpegで単色の背景動画を生成する（Pexels APIキーなし時のフォールバック）"""
    import subprocess
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path
    ], check=True, capture_output=True)
    return output_path
