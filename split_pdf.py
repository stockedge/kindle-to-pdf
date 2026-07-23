from __future__ import annotations

import argparse
import sys

from src.splitter import PdfSplitter


def main() -> None:
    parser = argparse.ArgumentParser(description="Split PDF into chunks")
    parser.add_argument("input_pdf", help="Path to the input PDF file")
    parser.add_argument(
        "--chunk-size",
        type=int,
        required=True,
        help="Number of pages per split file",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save split files (optional)",
    )

    args = parser.parse_args()

    if args.chunk_size < 1:
        print("Error: --chunk-size must be >= 1", file=sys.stderr)
        sys.exit(1)

    splitter = PdfSplitter()

    try:
        splitter.split_pdf(args.input_pdf, args.chunk_size, args.output_dir)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
