"""Wikipedia APIを使った画像取得モジュール（APIキー不要）"""
import requests
import anthropic
import os
from pathlib import Path


def extract_search_queries(script_text: str, n: int = 10) -> list[str]:
    """台本テキストからClaudeが人名・地名・装備名を抽出する（日英両方）。"""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    excerpt = script_text[:3000]
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                f"以下の台本から、Wikipediaで画像を検索するのに適したキーワードを{n}個抽出してください。\n"
                "人名・地名・軍事装備・組織名など固有名詞を優先してください。\n"
                "各キーワードを「日本語|英語」の形式で1行に1つ出力してください。\n"
                "例: 小泉進次郎|Shinjiro Koizumi\n"
                "例: F-35戦闘機|F-35 Lightning II\n"
                "説明不要。\n\n"
                + excerpt
            )
        }]
    )
    pairs = []
    for line in response.content[0].text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            ja, en = line.split("|", 1)
            pairs.append((ja.strip(), en.strip()))
        else:
            pairs.append((line, line))
    print(f"  画像検索クエリ: {[p[0] for p in pairs]}")
    return pairs[:n]


def get_wikipedia_image(query: str, lang: str = "ja") -> str | None:
    """
    Wikipedia記事のメイン画像URLを取得する。
    見つからない場合はNoneを返す。
    """
    try:
        # まず記事を検索
        r = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 3,
                "prop": "pageimages",
                "piprop": "original|thumbnail",
                "pithumbsize": 1280,
                "format": "json",
            },
            headers={"User-Agent": "YouTubeCreationBot/1.0"},
            timeout=15
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            original = page.get("original", {}).get("source")
            thumbnail = page.get("thumbnail", {}).get("source")
            url = original or thumbnail
            if url and not url.endswith(".svg"):
                return url
    except Exception as e:
        print(f"  Wikipedia検索失敗 ({lang}:{query}): {e}")
    return None


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
                        n_queries: int = 10, n_per_query: int = 2) -> list[str]:
    """
    台本から人名・地名を抽出し、Wikipedia記事のメイン画像をダウンロードする。
    日本語Wikipediaで見つからなければ英語Wikipediaにフォールバック。
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    query_pairs = extract_search_queries(script_text, n=n_queries)
    downloaded = []

    for qi, (ja_query, en_query) in enumerate(query_pairs):
        # 日本語Wikipedia → 英語Wikipediaの順で試す
        url = get_wikipedia_image(ja_query, lang="ja")
        if not url and en_query != ja_query:
            url = get_wikipedia_image(en_query, lang="en")

        if url:
            out_path = str(Path(output_dir) / f"img_{qi:02d}.jpg")
            if download_image(url, out_path):
                downloaded.append(out_path)
                print(f"  ✅ [{len(downloaded)}] {ja_query} → ダウンロード完了")
            else:
                print(f"  スキップ (DL失敗): {ja_query}")
        else:
            print(f"  スキップ (画像なし): {ja_query}")

    print(f"  台本関連画像: 計{len(downloaded)}枚取得")
    return downloaded
