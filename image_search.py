"""Wikimedia Commons APIを使った画像検索モジュール（APIキー不要）"""
import requests
import anthropic
import os
from pathlib import Path


def extract_search_queries(script_text: str, n: int = 8) -> list[str]:
    """台本テキストからClaudeが画像検索クエリを抽出する。"""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    excerpt = script_text[:3000]
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                f"以下の台本から、ニュース画像を検索するのに適したキーワードを{n}個抽出してください。\n"
                "人名・地名・軍事装備・政治的事件など具体的なものを優先してください。\n"
                "Wikimedia Commonsで検索しやすいよう、英語または日本語で出力してください。\n"
                "1行に1つ、説明不要。\n\n"
                + excerpt
            )
        }]
    )
    queries = [line.strip() for line in response.content[0].text.strip().splitlines() if line.strip()]
    print(f"  画像検索クエリ: {queries}")
    return queries[:n]


def search_images_wikimedia(query: str, n: int = 3) -> list[str]:
    """
    Wikimedia Commons APIで画像URLを検索する。APIキー不要。
    返り値: 画像URLのリスト
    """
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrnamespace": "6",  # File namespace
                "gsrsearch": query,
                "gsrlimit": n * 2,    # 多めに取得してフィルタ
                "prop": "imageinfo",
                "iiprop": "url|mime|size",
                "iiurlwidth": 1280,
                "format": "json",
            },
            headers={"User-Agent": "YouTubeCreationBot/1.0"},
            timeout=15
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        urls = []
        for page in pages.values():
            infos = page.get("imageinfo", [])
            for info in infos:
                mime = info.get("mime", "")
                if mime.startswith("image/") and "svg" not in mime:
                    url = info.get("thumburl") or info.get("url")
                    if url:
                        urls.append(url)
            if len(urls) >= n:
                break
        return urls[:n]
    except Exception as e:
        print(f"  画像検索失敗 ({query}): {e}")
        return []


def download_image(url: str, output_path: str) -> bool:
    """画像をダウンロードする。成功したらTrue。"""
    try:
        r = requests.get(url, stream=True, timeout=30,
                         headers={"User-Agent": "YouTubeCreationBot/1.0"})
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "image" not in content_type:
            return False
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception:
        return False


def fetch_script_images(script_text: str, output_dir: str,
                        n_queries: int = 8, n_per_query: int = 2) -> list[str]:
    """
    台本から画像検索クエリを抽出して、Wikimedia Commonsから関連画像をダウンロードする。
    返り値: ダウンロードした画像ファイルパスのリスト
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    queries = extract_search_queries(script_text, n=n_queries)
    downloaded = []

    for qi, query in enumerate(queries):
        urls = search_images_wikimedia(query, n=n_per_query)
        for ui, url in enumerate(urls):
            out_path = str(Path(output_dir) / f"img_{qi:02d}_{ui:02d}.jpg")
            if download_image(url, out_path):
                downloaded.append(out_path)
                print(f"  ✅ [{len(downloaded)}] {query} → ダウンロード完了")
            else:
                print(f"  スキップ: {query} ({url[:60]}...)")

    print(f"  台本関連画像: 計{len(downloaded)}枚取得")
    return downloaded
