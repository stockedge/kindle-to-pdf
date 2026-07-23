import argparse
import sys

from src.capturer import (
    DirectionDetectError,
    KindleCapturer,
    KindleWindowNotFoundError,
)
from src.converter import PdfConverter


def _configure_stdout():
    """Windows コンソールでも日本語が読めるように出力エンコーディングを整える。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def parse_size(size_str):
    """'1.8MB' のようなサイズ文字列をバイト数に変換する。"""
    size_str = size_str.upper().strip()
    units = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
    for unit, factor in units.items():
        if size_str.endswith(unit):
            try:
                return int(float(size_str[: -len(unit)]) * factor)
            except ValueError:
                return None
    try:
        return int(size_str)
    except ValueError:
        return None


def main():
    _configure_stdout()

    parser = argparse.ArgumentParser(
        description="Kindle for PC の書籍をキャプチャして PDF に変換します。"
    )
    parser.add_argument(
        "--output",
        default="output.pdf",
        help="出力 PDF ファイル名（デフォルト: output.pdf）",
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
        default=1.5,
        help="ページめくり後の待機秒数（デフォルト: 1.5）",
    )

    args = parser.parse_args()

    if args.delay < 0:
        print("エラー: --delay は 0 以上にしてください。")
        sys.exit(1)

    max_size_bytes = parse_size(args.max_size) if args.max_size else None
    if args.max_size and max_size_bytes is None:
        print(f"エラー: --max-size の形式が不正です: {args.max_size}")
        sys.exit(1)

    capturer = KindleCapturer(direction=args.direction, delay_sec=args.delay)
    converter = PdfConverter()

    print("=== Kindle for PC → PDF 変換 ===")
    print("1. Kindle for PC で対象の本を、できれば先頭付近で開いてください。")
    print("2. Enter を押すと、前面化・全画面化とページ送り方向の自動判定を行います。")
    print("3. キャプチャは最終ページ検出（または --pages）で自動停止します。")
    print("   緊急停止: Ctrl+C、またはマウスを画面左上へ移動")
    input("準備ができたら Enter を押してください...")

    try:
        capturer.prepare_kindle_window()
        capturer.wait_for_focus(3)
        capturer.detect_direction()
        capturer.capture_loop(args.temp_dir, args.pages)
        converter.convert_images_to_pdf(args.temp_dir, args.output, max_size_bytes)
    except KindleWindowNotFoundError as e:
        print(f"エラー: {e}")
        sys.exit(1)
    except DirectionDetectError as e:
        print(f"エラー: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
