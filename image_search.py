"""Serper.dev (Google画像検索) APIを使った画像取得モジュール"""
import requests
import anthropic
import os
from pathlib import Path
from config import SERPER_API_KEY


def extract_search_queries(script_text: str, n: int = 10) -> list[str]:
    """台本テキストからClaudeが画像検索クエリ（人名・地名・装備名）を抽出する。"""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    excerpt = script_text[:3000]
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                f"以下の台本から、Google画像検索するのに適したキーワードを{n}個抽出してください。\n"
                "人名・地名・軍事装備・政治的事件など具体的な固有名詞を優先してください。\n"
                "1行に1つ、日本語で出力してください。説明不要。\n\n"
                + excerpt
            )
        }]
    )
    queries = [line.strip() for line in response.content[0].text.strip().splitlines() if line.strip()]
    print(f"  画像検索クエリ: {queries}")
    return queries[:n]


def search_images(query: str, n: int = 3) -> list[str]:
    """
    Serper.dev の Google画像検索エンドポイントで画像URLを取得する。
    返り値: 画像URLのリスト
    """
    if not SERPER_API_KEY:
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/images",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "gl": "jp", "hl": "ja", "num": n * 2},
            timeout=15,
        )
        r.raise_for_status()
        images = r.json().get("images", [])
        urls = [img["imageUrl"] for img in images if img.get("imageUrl")]
        return urls[:n]
    except Exception as e:
        print(f"  画像検索失敗 ({query}): {e}")
        return []


def download_image(url: str, output_path: str) -> bool:
    """画像をダウンロードする。成功したらTrue。"""
    try:
        r = requests.get(url, stream=True, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "image" not in content_type:
            return False
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        # 極端に小さい画像（アイコン等）を除外
        if Path(output_path).stat().st_size < 5000:
            Path(output_path).unlink(missing_ok=True)
            return False
        return True
    except Exception:
        return False


def fetch_script_images(script_text: str, output_dir: str,
                        n_queries: int = 10, n_per_query: int = 2) -> list[str]:
    """
    台本から画像検索クエリを抽出して、Google画像検索で関連画像をダウンロードする。
    返り値: ダウンロードした画像ファイルパスのリスト
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    queries = extract_search_queries(script_text, n=n_queries)
    downloaded = []

    for qi, query in enumerate(queries):
        urls = search_images(query, n=n_per_query)
        got = 0
        for ui, url in enumerate(urls):
            if got >= n_per_query:
                break
            out_path = str(Path(output_dir) / f"img_{qi:02d}_{ui:02d}.jpg")
            if download_image(url, out_path):
                downloaded.append(out_path)
                got += 1
                print(f"  ✅ [{len(downloaded)}] {query} → ダウンロード完了")
            else:
                print(f"  スキップ: {query} ({url[:60]}...)")

    print(f"  台本関連画像: 計{len(downloaded)}枚取得")
    return downloaded
