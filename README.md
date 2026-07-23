# Kindle for PC to PDF Converter

Windows 版 Kindle for PC の書籍を自動キャプチャして PDF に変換するツールです。

## できること

- Kindle ウィンドウ（`Kindle.exe`）の自動検出・前面化・全画面化
- ページ送り方向（左右）の自動判定
- ページ静止の画像判定（連射キャプチャのフレーム差分）
- 最終ページの自動検出で停止
- 1ページ目 OCR による PDF ファイル名の自動命名
- 終了時の全画面解除・マウスカーソル復元
- PDF サイズ上限での自動分割

## 前提条件

- **Windows OS**（WSL 不可）
- [uv](https://docs.astral.sh/uv/)
- Kindle for PC
- 日本語 OCR を使う場合は、Windows の日本語 OCR 機能が有効であること

## セットアップ

uv 未導入の場合:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

依存関係のインストール（仮想環境も自動作成）:

```powershell
uv sync
```

開発用（Playwright / Ruff / mypy）も含める場合:

```powershell
uv sync --group dev
```

型検査・リント・フォーマット:

```powershell
uv run mypy
uv run ruff check .
uv run ruff format .
```

## 使い方

1. Kindle for PC で対象の本を、できれば**先頭付近**で開く
2. このフォルダで実行する:

```powershell
uv run python main.py
```

3. Enter を押す  
   以降は自動で進みます（前面化 → 全画面 → 案内消去待ち → 方向判定 → キャプチャ → PDF 生成 → 全画面解除）。

### 実行中の挙動

| 項目 | 内容 |
|------|------|
| ウィンドウ | `Kindle.exe` を検出して前面化・全画面化。案内（F11で終了…）が消えるまで待機 |
| マウス | 文字に被らないよう右下へ退避し、カーソル非表示 |
| ページ判定 | 連射キャプチャし、フレーム間差分が小さくなったら保存 |
| 終了 | 最終ページ検出、または `--pages` 到達で自動停止 |
| ファイル名 | `--output` 省略時は 1 ページ目 OCR から自動命名 |
| 後始末 | 全画面解除、カーソル復元 |

途中停止はターミナルで **Ctrl+C** です。

## オプション

```powershell
# いちばん簡単（ファイル名も自動）
uv run python main.py

# 出力名を指定
uv run python main.py --output my_book.pdf

# OCR 自動命名の文字数（デフォルト: 40）
uv run python main.py --name-chars 20

# ページ数上限（最終ページ検出より先に止まる）
uv run python main.py --pages 100

# ページ送り方向を手動指定（自動判定が失敗したとき）
uv run python main.py --direction ltr
uv run python main.py --direction rtl

# PDF サイズ上限（デフォルト: 180MB。超えると分割）
uv run python main.py --max-size 50MB

# 静止待ちの最大秒数（アニメが長くて崩れるとき）
uv run python main.py --delay 3.0

# スクリーンショット保存先（デフォルト: screenshots）
uv run python main.py --temp-dir screenshots
```

| オプション | デフォルト | 説明 |
|------------|------------|------|
| `--output` | （OCR 自動） | 出力 PDF 名 |
| `--name-chars` | `40` | OCR から使う最大文字数 |
| `--pages` | なし | キャプチャ枚数の上限 |
| `--direction` | `auto` | `auto` / `ltr` / `rtl` |
| `--max-size` | `180MB` | PDF サイズ上限 |
| `--delay` | `2.0` | ページめくり後の静止待ち最大秒数 |
| `--temp-dir` | `screenshots` | 一時画像ディレクトリ |

## OCR について

- Windows 標準 OCR（`winocr`、言語 `ja`）を使用します
- 先頭行の文字をファイル名に使います（無効な文字は除去）
- 失敗時は `kindle_book_日時.pdf` になります
- 日本語が認識できない場合は、Windows の「オプション機能」から日本語 OCR を追加してください

## PDF のページ分割（任意）

サイズ分割とは別に、完成 PDF をページ数で分割できます。

```powershell
uv run python split_pdf.py my_book.pdf --chunk-size 50
uv run python split_pdf.py my_book.pdf --chunk-size 50 --output-dir output
```

## うまくいかないとき

| 症状 | 対処 |
|------|------|
| Cursor など別窓を掴む | 最新版では `Kindle.exe` のみ対象。Kindle を起動して再実行 |
| めくり途中の画像が混ざる | `--delay 3.0` など待機を延ばす |
| ページ送り方向が逆 | `--direction ltr` または `--direction rtl` |
| 最終ページで止まらない | `--pages` で枚数指定するか Ctrl+C |
| OCR 名がおかしい | `--output` で手動指定、または `--name-chars` を調整 |
| 全画面のまま残る | 手動で F11。通常は終了時に自動解除されます |
| `uv` が見つからない | [uv のインストール手順](https://docs.astral.sh/uv/getting-started/installation/) を確認 |

## 注意

- 自分で購入・利用権限のある書籍の、私的利用の範囲で使ってください
- キャプチャ中は Kindle ウィンドウを操作しないでください
