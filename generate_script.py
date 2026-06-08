"""
Claude APIを使った軍事系YouTube台本自動生成モジュール
"""
import os
import re
import anthropic
from pathlib import Path
from config import SCRIPTS_DIR

# 台本生成に使うモデル
MODEL = "claude-opus-4-8"

# 台本生成プロンプト（指示書に基づく）
SYSTEM_PROMPT = """あなたは軍事系YouTubeチャンネルの専門台本ライターです。
以下の方針に従って、AI音声読み上げ用の高品質な台本を制作してください。

## 基本方針
- 軍事をメインテーマに、科学・経済・歴史・地政学を掛け合わせた切り口
- 必ず日本の視点・安全保障への影響・技術力を含める
- AI音声での読み上げに最適化した自然な話し言葉

## 章立て構造（7章＋導入部）
1. 導入部（冒頭で衝撃的事実・数値を提示し、動画で解明する内容を予告）
2. 第1章：衝撃的事実の提示
3. 第2章：基礎となる技術や背景の解説
4. 第3章：詳細分析と掛け合わせ要素の深掘り
5. 第4章：他国との比較検証
6. 第5章：限界・課題・問題点の指摘
7. 第6章：軍事的影響・戦略的意味
8. 第7章：日本の対応・技術力・未来展望（締めくくり）

## 語り口調
- です・ます調で自然な語りかけ
- 「そして」「しかし」「つまり」「実は」「意外にも」で流れを作る
- 「防衛白書によると」「元海自幹部が証言」などの権威付け
- 「日本の技術力」「自衛隊の実力」「我が国の対応能力」の愛国心訴求
- 煽り・緊迫感（「従来の常識を覆す」「隠された真実」「日本が直面する現実」）
- 章ごとに次章への期待を持たせる締め

## AI音声用ルール
- 難読漢字は平仮名に（例：「艦艇」→「かんてい」は不要だが「轟沈」→「ごうちん」と読み仮名）
- 数字は読みやすく（「3つ」「5機」「約90キロメートル」）
- 英語略語は初出時に読み方（「F-35（エフサンジュウゴ）」）
- 適切な句読点で息継ぎを確保
- 1文は60文字以内を目安に

## アウトプット形式
以下のフォーマットで出力してください。## や # はセクション区切りとして使用。
本文中の各段落は「。」で終わる完結した文のまとまりで記述してください。

```
## title: タイトル
## background: Pexels検索キーワード（英語3〜5語）

---

## 導入部

（ナレーション本文。1〜2文のまとまりで改行）

## 第1章 〇〇

（ナレーション本文）

## 第2章 〇〇

（ナレーション本文）

...

## 第7章 〇〇

（ナレーション本文）
```"""


def generate(topic: str, additional_context: str = "") -> str:
    """
    トピックから台本テキストを生成してClaudeに依頼する。
    返り値: 台本テキスト（ファイル保存前の生文字列）
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_message = f"""以下のテーマで軍事系YouTube台本を制作してください。

テーマ: {topic}
{f'追加情報・コンテキスト: {additional_context}' if additional_context else ''}

【要件】
- 全体で10〜20分相当の分量（約6,000〜12,000文字）
- 必ず最新の軍事動向・日本の安全保障視点を含める
- 指定フォーマットで出力すること
- Pexels検索キーワードは英語で動画背景に合うもの（例: "military warship ocean", "japan defense technology"）"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    return response.content[0].text


def save_script(content: str, filename: str | None = None) -> str:
    """台本をscripts/ディレクトリに保存する"""
    Path(SCRIPTS_DIR).mkdir(parents=True, exist_ok=True)

    if filename is None:
        import time
        # タイムスタンプベースのASCIIファイル名（日本語パスによるFFmpegエラーを回避）
        filename = f"script_{int(time.time())}.txt"
    elif not filename.endswith(".txt"):
        filename = filename + ".txt"

    output_path = Path(SCRIPTS_DIR) / filename
    output_path.write_text(content, encoding="utf-8")
    return str(output_path)


def split_into_lines(text: str, max_chars: int = 55) -> list[str]:
    """
    台本テキストを字幕・音声読み上げ単位の行に分割する。
    「。」「！」「？」で区切り、max_chars文字を超える場合は読点で再分割。
    """
    # 文末で分割
    sentences = re.split(r'(?<=[。！？])', text)
    lines = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) <= max_chars:
            lines.append(sentence)
        else:
            # 長い文は読点で再分割を試みる（短すぎる断片はまとめる）
            parts = re.split(r'(?<=[、])', sentence)
            current = ""
            for part in parts:
                if len(current) + len(part) <= max_chars:
                    current += part
                else:
                    if current and len(current) >= 10:
                        lines.append(current.strip())
                        current = part
                    else:
                        current += part  # 短すぎる場合は次とまとめる
            if current.strip():
                lines.append(current.strip())

    return [l for l in lines if l.strip()]


def parse_chapter_script(script_path: str) -> tuple[list[str], dict]:
    """
    章立て形式の台本ファイルをパースして字幕行リストとメタデータを返す。
    ## で始まる行はセクション区切り（音声なし）として扱う。
    """
    content = Path(script_path).read_text(encoding="utf-8")
    meta = {}
    all_lines = []

    in_script = False
    current_section_text = ""

    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("## title:") or stripped.startswith("## background:"):
            # メタデータ
            kv = stripped[2:].strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
                meta[k.strip()] = v.strip()

        elif stripped == "---":
            in_script = True

        elif in_script:
            if stripped.startswith("## "):
                # セクション区切り → 直前のテキストを処理してから章タイトル行を追加
                if current_section_text.strip():
                    all_lines.extend(split_into_lines(current_section_text.strip()))
                    current_section_text = ""
                # 章タイトルは空行として区切りを入れる（音声は短い無音）
                all_lines.append("")  # セクション間の間（無音）
            elif stripped:
                current_section_text += stripped

    # 最後のセクション
    if current_section_text.strip():
        all_lines.extend(split_into_lines(current_section_text.strip()))

    return all_lines, meta


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Claude APIで軍事系YouTube台本を生成する")
    parser.add_argument("topic", help="動画のテーマ・トピック")
    parser.add_argument("-o", "--output", help="出力ファイル名")
    parser.add_argument("--context", help="追加コンテキスト・情報", default="")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)

    print(f"台本生成中: '{args.topic}' ...")
    script = generate(args.topic, args.context)
    path = save_script(script, args.output)
    print(f"✅ 台本保存: {path}")
    print(f"   文字数: {len(script):,}")
