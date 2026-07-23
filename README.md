# Kindle for PC to PDF Converter

Windows 版 Kindle for PC の書籍をキャプチャして PDF に変換するツールです。

## 前提条件
- **Windows OS** 上で実行する必要があります（WSL不可）。
- Python がインストールされていること。
- Kindle for PC がインストールされていること。

## インストール

1. このフォルダを Windows 上の適当な場所に配置します。
2. 依存ライブラリをインストールします:
   ```powershell
   pip install -r requirements.txt
   ```

## 実行方法

1. Kindle for PC で対象の本を、できれば**先頭付近**で開きます。

2. コマンドプロンプトまたは PowerShell でこのフォルダを開き、スクリプトを実行します:
   ```powershell
   python main.py --output my_book.pdf
   ```

3. Enter を押すと、前面化・全画面化と**ページ送り方向の自動判定**のあと、キャプチャを開始します。
   - 最終ページを検出すると**自動停止**します（Ctrl+C は不要）。
   - 途中で止めたい場合は、このターミナルで **Ctrl+C**、またはマウスを画面左上へ急激に動かしてください。

4. 終了後、`my_book.pdf` が生成されます。

### よく使うオプション

ページ数を指定する場合（自動停止より先に上限で止まります）:
```powershell
python main.py --output my_book.pdf --pages 100
```

ページ送り方向を手動指定する場合（自動判定が失敗したとき）:
```powershell
python main.py --output my_book.pdf --direction rtl
python main.py --output my_book.pdf --direction ltr
```

PDF のサイズ上限（デフォルト: 180MB。超えると分割されます）:
```powershell
python main.py --output my_book.pdf --max-size 50MB
```

ページめくり後の待機秒数（表示が遅い・ずれる場合に調整）:
```powershell
python main.py --output my_book.pdf --delay 2.0
```
