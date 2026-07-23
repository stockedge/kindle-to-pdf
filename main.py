from __future__ import annotations

import argparse
import contextlib
import sys
from typing import cast

from src.capturer import (
    DirectionDetectError,
    KindleCapturer,
    KindleWindowNotFoundError,
)
from src.converter import PdfConverter
from src.ocr_namer import suggest_output_filename
from src.types import PageDirection


def _configure_stdout() -> None:
    """Windows コンソールでも日本語が読めるように出力エンコーディングを整える。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8")


def parse_size(size_str: str) -> int | None:
    """'1.8MB' のようなサイズ文字列をバイト数に変換する。"""
    normalized = size_str.upper().strip()
    units: dict[str, int] = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
    for unit, factor in units.items():
        if normalized.endswith(unit):
            try:
                return int(float(normalized[: -len(unit)]) * factor)
            except ValueError:
                return None
    try:
        return int(normalized)
    except ValueError:
        return None


def main() -> None:
    _configure_stdout()

    parser = argparse.ArgumentParser(
        description="Kindle for PC の書籍をキャプチャして PDF に変換します。"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="出力 PDF ファイル名（省略時は1ページ目の OCR から自動命名）",
    )
    parser.add_argument(
        "--name-chars",
        type=int,
        default=40,
        help="OCR 自動命名で使う最大文字数（デフォルト: 40）",
    )
    parser.add_argument(
        "--temp-dir",
        default="screenshots",
        help="スクリーンショット用の一時ディレクトリ（デフォルト: screenshots）",
    )
    parser.add_argument(
        "--pages",
        type=int,
        help="キャプチャするページ数（省略時は最終ページ検出まで）",
    )
    parser.add_argument(
        "--direction",
        choices=["auto", "ltr", "rtl"],
        default="auto",
        help="ページ送り方向: auto（自動判定・デフォルト）、ltr、rtl",
    )
    parser.add_argument(
        "--max-size",
        default="180MB",
        help="生成 PDF のサイズ上限（例: 50MB）。デフォルト: 180MB",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="ページめくり後の静止待ち最大秒数（連射差分が小さくなるまで待機。デフォルト: 2.0）",
    )

    args = parser.parse_args()

    if args.delay < 0:
        print("エラー: --delay は 0 以上にしてください。")
        sys.exit(1)
    if args.name_chars < 1:
        print("エラー: --name-chars は 1 以上にしてください。")
        sys.exit(1)

    max_size_bytes = parse_size(args.max_size) if args.max_size else None
    if args.max_size and max_size_bytes is None:
        print(f"エラー: --max-size の形式が不正です: {args.max_size}")
        sys.exit(1)

    direction = cast(PageDirection, args.direction)
    capturer = KindleCapturer(direction=direction, delay_sec=args.delay)
    converter = PdfConverter()

    print("=== Kindle for PC → PDF 変換 ===")
    print("1. Kindle for PC で対象の本を、できれば先頭付近で開いてください。")
    print("2. Enter を押すと、前面化・全画面化とページ送り方向の自動判定を行います。")
    print("3. キャプチャは最終ページ検出（または --pages）で自動停止します。")
    if args.output:
        print(f"4. 出力ファイル: {args.output}")
    else:
        print("4. 出力ファイル名は1ページ目の OCR から自動決定します。")
    print("   緊急停止: Ctrl+C")
    input("準備ができたら Enter を押してください...")

    try:
        capturer.prepare_kindle_window()
        capturer.wait_for_focus(2)
        capturer.detect_direction()
        capturer.capture_loop(args.temp_dir, args.pages)

        output_path: str | None = args.output
        if not output_path:
            output_path = suggest_output_filename(args.temp_dir, max_chars=args.name_chars)

        converter.convert_images_to_pdf(args.temp_dir, output_path, max_size_bytes)
    except KindleWindowNotFoundError as e:
        print(f"エラー: {e}")
        sys.exit(1)
    except DirectionDetectError as e:
        print(f"エラー: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        sys.exit(1)
    finally:
        # 方向判定失敗時など、capture_loop に入る前に落ちても全画面を戻す
        capturer.exit_fullscreen_if_needed()


if __name__ == "__main__":
    main()
