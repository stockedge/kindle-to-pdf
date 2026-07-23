import glob
import os
import re
from datetime import datetime

from PIL import Image


# Windows ファイル名に使えない文字
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# CJK 文字の間に入った余分な空白を除去（Windows OCR の癖）
_CJK_SPACES = re.compile(
    r"(?<=[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f])\s+(?=[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f])"
)


def suggest_output_filename(image_dir, max_chars=40, lang="ja"):
    """1ページ目を OCR し、先頭文字から PDF ファイル名を作る。

    Args:
        image_dir: スクリーンショットディレクトリ
        max_chars: ファイル名に使う最大文字数（拡張子除く）
        lang: Windows OCR の言語コード（日本語は ja）

    Returns:
        例: "人工知能の基礎と応用.pdf"
    """
    first_page = _find_first_page(image_dir)
    if first_page is None:
        print("OCR 用の1ページ目画像が見つかりません。フォールバック名を使います。")
        return _fallback_filename()

    print(f"1ページ目を OCR してファイル名を決定します: {first_page}")
    try:
        text = _ocr_image(first_page, lang=lang)
    except Exception as e:
        print(f"OCR に失敗しました: {e}")
        print("フォールバック名を使います。")
        return _fallback_filename()

    filename_stem = sanitize_filename_stem(text, max_chars=max_chars)
    if not filename_stem:
        print("OCR 結果から有効なファイル名を作れませんでした。フォールバック名を使います。")
        return _fallback_filename()

    print(f"OCR 結果（抜粋）: {text[:80]!r}")
    print(f"出力ファイル名: {filename_stem}.pdf")
    return f"{filename_stem}.pdf"


def sanitize_filename_stem(text, max_chars=40):
    """OCR テキストから Windows 向けのファイル名本体を作る。"""
    if not text:
        return ""

    # 先頭行を優先（タイトルが来る想定）
    first_line = text.splitlines()[0] if "\n" in text else text
    normalized = _CJK_SPACES.sub("", first_line)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = _INVALID_FILENAME_CHARS.sub("", normalized)
    normalized = normalized.strip(" .")

    if len(normalized) > max_chars:
        normalized = normalized[:max_chars].rstrip(" .")

    return normalized


def _find_first_page(image_dir):
    pages = sorted(glob.glob(os.path.join(image_dir, "page_*.png")))
    return pages[0] if pages else None


def _ocr_image(image_path, lang="ja"):
    """Windows OCR (winocr) で画像からテキストを取得する。"""
    from winocr import recognize_pil_sync

    image = Image.open(image_path)
    result = recognize_pil_sync(image, lang=lang)

    if isinstance(result, dict):
        lines = result.get("lines") or []
        if lines:
            line_texts = []
            for line in lines:
                line_text = line.get("text") if isinstance(line, dict) else str(line)
                if line_text:
                    line_texts.append(_CJK_SPACES.sub("", line_text).strip())
            if line_texts:
                return "\n".join(line_texts)
        text = result.get("text") or ""
        return _CJK_SPACES.sub("", text).strip()

    return _CJK_SPACES.sub("", str(result)).strip()


def _fallback_filename():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"kindle_book_{stamp}.pdf"
