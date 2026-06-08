# YouTube動画自動生成パイプライン

ニュース解説系・フル背景動画＋字幕スタイルのYouTube動画を自動生成します。

## 構成

```
台本テキスト
  → VOICEVOX（音声合成）
  → Pexels API（フリー背景動画）
  → FFmpeg（字幕焼き込み＋動画合成）
  → MP4完成
```

## セットアップ

### 1. 依存パッケージのインストール
```bash
pip install -r requirements.txt
sudo apt install ffmpeg  # FFmpegが未インストールの場合
```

### 2. 環境変数の設定
```bash
cp .env.example .env
# .envを編集してAPIキーを設定
```

**必要なもの:**
- [VOICEVOX](https://voicevox.hiroshiba.jp/) — ローカルに起動
- [Pexels APIキー](https://www.pexels.com/api/) — 無料登録

### 3. VOICEVOXの起動
VOICEVOX GUIアプリを起動するか、Engineのみを起動してください。
```bash
# Engine単体起動の場合
./voicevox_engine/run.sh
```

## 使い方

```bash
# 台本ファイルを指定して生成
python main.py scripts/sample_news.txt

# 出力ファイル名を指定
python main.py scripts/sample_news.txt -o my_video

# 背景キーワードを上書き
python main.py scripts/sample_news.txt --bg "ocean waves calm"

# テスト用（Pexels不要・黒背景）
python main.py scripts/sample_news.txt --solid-bg

# 利用可能なVOICEVOXスピーカー一覧
python main.py --list-speakers
```

## 台本ファイルの書き方

```
## title: 動画タイトル
## background: city night  ← Pexels検索キーワード（英語）

---
ナレーション1行目
ナレーション2行目
...
```

- `---` より上がメタデータ、以下がナレーション
- 1行が1字幕に対応
- 空行は0.5秒の無音になる

## ファイル構成

```
├── main.py          # エントリーポイント
├── voicevox.py      # VOICEVOX API連携
├── pexels.py        # Pexels API・背景動画取得
├── subtitle.py      # SRT/ASS字幕生成
├── video.py         # FFmpeg動画合成
├── config.py        # 設定値管理
├── scripts/         # 台本ファイル置き場
└── output/          # 生成動画の出力先
```
