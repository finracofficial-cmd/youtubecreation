"""Google Custom Search APIを使った画像検索モジュール"""
import requests
import anthropic
import os
from pathlib import Path
from config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID


def extract_search_queries(script_text: str, n: int = 8) -> list[str]:
    """
    台本テキストからClaudeが画像検索クエリを抽出する。
    人名・地名・軍事装備・事件名などを日本語で返す。
    """
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
    Google Custom Search APIで画像URLを検索する。
    返り値: 画像URLのリスト
    """
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        return []

    try:
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": GOOGLE_CSE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "searchType": "image",
                "num": n,
                "imgSize": "large",
                "safe": "active",
            },
            timeout=15
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        return [item["link"] for item in items if "link" in item]
    except Exception as e:
        print(f"  画像検索失敗 ({query}): {e}")
        return []


def download_image(url: str, output_path: str) -> bool:
    """画像をダウンロードする。成功したらTrue。"""
    try:
        r = requests.get(url, stream=True, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        # 画像以外のコンテンツを除外
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
    台本から画像検索クエリを抽出して、関連画像をまとめてダウンロードする。
    返り値: ダウンロードした画像ファイルパスのリスト
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    queries = extract_search_queries(script_text, n=n_queries)
    downloaded = []

    for qi, query in enumerate(queries):
        urls = search_images(query, n=n_per_query)
        for ui, url in enumerate(urls):
            out_path = str(Path(output_dir) / f"img_{qi:02d}_{ui:02d}.jpg")
            if download_image(url, out_path):
                downloaded.append(out_path)
                print(f"  ✅ [{len(downloaded)}] {query} → ダウンロード完了")
            else:
                print(f"  スキップ: {query} ({url[:50]}...)")

    print(f"  台本関連画像: 計{len(downloaded)}枚取得")
    return downloaded
