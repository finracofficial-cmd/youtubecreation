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


def get_best_url(video: dict) -> str | None:
    """動画オブジェクトから最適なURLを取得する（品質優先順）"""
    files = video.get("video_files", [])
    if not files:
        return None
    # 品質優先: hd > sd > 4k > uhd > その他
    for quality in ("hd", "sd", "4k", "uhd", "hls"):
        for f in files:
            if f.get("quality") == quality and f.get("link"):
                return f["link"]
    # qualityフィールドが一致しない場合は最初の有効なリンクを返す
    for f in files:
        if f.get("link"):
            return f["link"]
    return None


def download_video(url: str, output_path: str) -> str:
    """動画をダウンロードして保存する"""
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    return output_path


def fetch_background(query: str, output_path: str, prefer_index: int | None = None) -> str:
    """
    キーワードに合う背景動画を検索してダウンロードする。
    全ての取得動画を順に試し、URLが取得できた最初の動画を使用する。
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    videos = search_videos(query, per_page=15)
    if not videos:
        raise ValueError(f"'{query}' に一致する動画が見つかりませんでした")

    # prefer_indexが指定されている場合はその動画を先頭に
    if prefer_index is not None:
        idx = prefer_index % len(videos)
        ordered = [videos[idx]] + [v for i, v in enumerate(videos) if i != idx]
    else:
        ordered = list(videos)
        random.shuffle(ordered)

    for video in ordered:
        url = get_best_url(video)
        if url:
            print(f"  背景動画: Pexels ID={video['id']} をダウンロード中...")
            return download_video(url, output_path)

    raise ValueError(f"'{query}' の検索結果 {len(videos)} 件全てでURLが取得できませんでした")

def fetch_multiple_backgrounds(query: str, output_dir: str, n: int = 8) -> list[str]:
    """
    キーワードで複数の背景動画を検索・ダウンロードする。
    返り値: ダウンロードした動画ファイルパスのリスト
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    videos = search_videos(query, per_page=min(n * 2, 30))  # 余裕を持って取得
    if not videos:
        raise ValueError(f"'{query}' に一致する動画が見つかりませんでした")

    random.shuffle(videos)
    downloaded = []
    for i, video in enumerate(videos):
        if len(downloaded) >= n:
            break
        url = get_best_url(video)
        if not url:
            continue
        out_path = str(Path(output_dir) / f"clip_{i:02d}.mp4")
        try:
            print(f"  [{len(downloaded)+1}/{n}] Pexels ID={video['id']} ダウンロード中...")
            download_video(url, out_path)
            downloaded.append(out_path)
        except Exception as e:
            print(f"  スキップ（ダウンロード失敗: {e}）")

    if not downloaded:
        raise ValueError(f"'{query}' の動画を1件もダウンロードできませんでした")
    return downloaded


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
