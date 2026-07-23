import glob
import os

import img2pdf


class PdfConverter:
    def convert_images_to_pdf(self, image_dir, output_filename, max_size_bytes=None):
        """ディレクトリ内の画像を PDF に変換する。サイズ上限超過時は分割する。"""
        print(f"{image_dir} 内の画像を {output_filename} に変換しています...")

        images = sorted(glob.glob(os.path.join(image_dir, "*.png")))

        if not images:
            print("変換する画像が見つかりませんでした。")
            return

        if max_size_bytes is None:
            try:
                with open(output_filename, "wb") as f:
                    f.write(img2pdf.convert(images))
                print(f"作成完了: {output_filename}（{len(images)} ページ）")
            except Exception as e:
                print(f"PDF の作成に失敗しました: {e}")
            return

        current_batch = []
        current_size = 0
        part_num = 1
        base_name, ext = os.path.splitext(output_filename)

        for img_path in images:
            img_size = os.path.getsize(img_path)

            if current_batch and (current_size + img_size > max_size_bytes):
                self._write_batch(current_batch, f"{base_name}_part_{part_num}{ext}")
                part_num += 1
                current_batch = []
                current_size = 0

            current_batch.append(img_path)
            current_size += img_size

        if current_batch:
            # 分割が発生しなかった場合は part なしのファイル名で保存
            if part_num == 1:
                self._write_batch(current_batch, output_filename)
            else:
                self._write_batch(current_batch, f"{base_name}_part_{part_num}{ext}")

    def _write_batch(self, images, output_filename):
        try:
            with open(output_filename, "wb") as f:
                f.write(img2pdf.convert(images))
            print(f"作成完了: {output_filename}（{len(images)} ページ）")
        except Exception as e:
            print(f"PDF の作成に失敗しました ({output_filename}): {e}")
