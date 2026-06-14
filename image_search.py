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


def extract_video_queries(script_text: str, n: int = 12) -> list[str]:
    """
    台本テキストからPexels動画検索に適した英語キーワードをClaudeが抽出する。
    Pexelsはフリー素材なので人物固有名詞ではなく情景・場所・テーマで検索する。
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    excerpt = script_text[:3000]
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": (
                f"以下の台本の内容・テーマに合ったPexels動画検索用の英語キーワードを{n}個考えてください。\n"
                "以下の3カテゴリをバランスよく混ぜてください：\n"
                "① 台本の主題に直結する場面（例: 皇室→「imperial palace ceremony」「royal procession」）\n"
                "② 台本の雰囲気・感情に合う映像（例: 緊張感→「city traffic night」「storm clouds」）\n"
                "③ 汎用的な背景として使える映像（例:「japan aerial view」「parliament building」「news studio」）\n"
                "Pexelsにありそうな具体的な英語フレーズで出力してください。\n"
                "1行に1つ、説明不要。\n\n"
                + excerpt
            )
        }]
    )
    queries = [line.strip() for line in response.content[0].text.strip().splitlines() if line.strip()]
    # 番号付きリストの番号を除去
    cleaned = []
    for q in queries:
        q = q.lstrip("0123456789.-) ").strip()
        if q:
            cleaned.append(q)
    print(f"  動画検索クエリ: {cleaned}")
    return cleaned[:n]


# 動画背景に耐える最低解像度（横幅・縦幅）
MIN_IMAGE_WIDTH = 800
MIN_IMAGE_HEIGHT = 600


def search_images(query: str, n: int = 3) -> list[str]:
    """
    Serper.dev の Google画像検索エンドポイントで画像URLを取得する。
    解像度の高い順にソートし、低解像度の画像は除外する。
    返り値: 画像URLのリスト（高画質順）
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
            # 多めに取得して解像度でフィルタ・ソートする
            json={"q": query, "gl": "jp", "hl": "ja", "num": max(n * 5, 20)},
            timeout=15,
        )
        r.raise_for_status()
        images = r.json().get("images", [])

        # 解像度が取得でき、かつ最低基準を満たすものだけ残す
        candidates = []
        for img in images:
            url = img.get("imageUrl")
            w = img.get("imageWidth", 0) or 0
            h = img.get("imageHeight", 0) or 0
            if not url:
                continue
            if w >= MIN_IMAGE_WIDTH and h >= MIN_IMAGE_HEIGHT:
                candidates.append((url, w * h))

        # 解像度（面積）の大きい順にソート
        candidates.sort(key=lambda x: x[1], reverse=True)

        # 基準を満たすものが少なければ、解像度不明/小さめも補充
        if len(candidates) < n:
            for img in images:
                url = img.get("imageUrl")
                if url and url not in [c[0] for c in candidates]:
                    candidates.append((url, 0))

        return [url for url, _ in candidates[:n]]
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
        # 低品質・アイコン・破損画像を除外（高画質背景には30KB以上が目安）
        if Path(output_path).stat().st_size < 30000:
            Path(output_path).unlink(missing_ok=True)
            return False
        return True
    except Exception:
        Path(output_path).unlink(missing_ok=True)
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
