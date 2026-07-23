from __future__ import annotations

import os

from pypdf import PdfReader, PdfWriter


class PdfSplitter:
    def split_pdf(
        self,
        input_path: str,
        chunk_size: int,
        output_dir: str | None = None,
    ) -> None:
        """PDF を指定ページ数ごとのチャンクに分割する。

        Args:
            input_path: 入力 PDF のパス。
            chunk_size: 分割後ファイルあたりのページ数。
            output_dir: 出力先ディレクトリ。省略時は入力ファイルと同じ場所。
        """
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        resolved_output_dir = output_dir if output_dir is not None else os.path.dirname(input_path)
        if resolved_output_dir == "":
            resolved_output_dir = "."

        if not os.path.exists(resolved_output_dir):
            os.makedirs(resolved_output_dir)

        reader = PdfReader(input_path)
        total_pages = len(reader.pages)

        base_name = os.path.splitext(os.path.basename(input_path))[0]

        print(f"Splitting {input_path} ({total_pages} pages) into chunks of {chunk_size} pages...")

        for i in range(0, total_pages, chunk_size):
            writer = PdfWriter()
            end_page = min(i + chunk_size, total_pages)

            for page_num in range(i, end_page):
                writer.add_page(reader.pages[page_num])

            output_filename = f"{base_name}_part_{i // chunk_size + 1}.pdf"
            output_path = os.path.join(resolved_output_dir, output_filename)

            with open(output_path, "wb") as f:
                writer.write(f)

            print(f"Created {output_filename} (pages {i + 1}-{end_page})")

        print("Splitting complete.")
