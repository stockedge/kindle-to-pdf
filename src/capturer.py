import os
import time
from datetime import timedelta

import pyautogui
import pygetwindow as gw
from PIL import Image, ImageChops


# 縮小後の平均二乗誤差がこの値以下なら「ほぼ同一ページ」とみなす
_SAME_PAGE_MSE_THRESHOLD = 5.0
# 連続して同一と判定された回数がこの値以上で最終ページ到達とみなす
_SAME_PAGE_STREAK_TO_STOP = 2
# 比較用に縮小する一辺のピクセル数
_COMPARE_SIZE = (64, 64)


class KindleWindowNotFoundError(Exception):
    """Kindle for PC のウィンドウが見つからない場合。"""


class DirectionDetectError(Exception):
    """ページ送り方向を自動判定できなかった場合。"""


class KindleCapturer:
    def __init__(self, direction="auto", delay_sec=1.5):
        self.direction = direction
        self.delay_sec = delay_sec
        # マウスを画面左上へ急激に動かすと緊急停止
        pyautogui.FAILSAFE = True

    def prepare_kindle_window(self):
        """Kindle ウィンドウを検出し、前面化・最大化・全画面化を試行する。"""
        kindle_window = self._find_kindle_window()
        if kindle_window is None:
            raise KindleWindowNotFoundError(
                "Kindle for PC のウィンドウが見つかりません。"
                "Kindle for PC で本を開いてから再実行してください。"
            )

        print(f"Kindle ウィンドウを検出: {kindle_window.title}")
        try:
            if kindle_window.isMinimized:
                kindle_window.restore()
            kindle_window.activate()
            time.sleep(0.3)
            kindle_window.maximize()
            time.sleep(0.3)
        except Exception as e:
            print(f"ウィンドウの前面化に失敗しました: {e}")
            print("手動で Kindle ウィンドウを前面にしてください。")

        # 全画面表示を試行（すでに全画面でも害は小さい）
        pyautogui.press("f11")
        time.sleep(0.5)
        print("Kindle ウィンドウを前面化し、全画面化を試行しました。")

    def wait_for_focus(self, seconds=3):
        """キャプチャ開始前の短いカウントダウン。"""
        print("ウィンドウを触らずにそのままお待ちください。")
        for remaining in range(seconds, 0, -1):
            print(f"開始まで {remaining} 秒...")
            time.sleep(1)
        print("キャプチャを開始します。")

    def detect_direction(self):
        """右キー・左キーを試し、ページが変わる方向を判定する。元のページに戻す。"""
        if self.direction in ("ltr", "rtl"):
            label = "右送り (ltr)" if self.direction == "ltr" else "左送り (rtl)"
            print(f"ページ送り方向: {label}（指定値）")
            return self.direction

        print("ページ送り方向を自動判定しています...")
        print("※ 本の先頭付近で実行してください（最終ページだと誤判定することがあります）。")

        baseline = pyautogui.screenshot()

        # まず右キー（横書き・ltr で次ページ）
        pyautogui.press("right")
        time.sleep(self.delay_sec)
        after_right = pyautogui.screenshot()

        if not self._images_are_nearly_identical(baseline, after_right):
            # 進めたので左キーで元のページへ戻す
            pyautogui.press("left")
            time.sleep(self.delay_sec)
            self.direction = "ltr"
            print("ページ送り方向: 右送り (ltr) と判定しました。")
            return self.direction

        # 右では変わらない → 左キーを試す（縦書き・rtl）
        pyautogui.press("left")
        time.sleep(self.delay_sec)
        after_left = pyautogui.screenshot()

        if not self._images_are_nearly_identical(baseline, after_left):
            # 進めたので右キーで元のページへ戻す
            pyautogui.press("right")
            time.sleep(self.delay_sec)
            self.direction = "rtl"
            print("ページ送り方向: 左送り (rtl) と判定しました。")
            return self.direction

        raise DirectionDetectError(
            "ページ送り方向を判定できませんでした。"
            "本の先頭付近で開き直すか、--direction ltr または --direction rtl を指定してください。"
        )

    def capture_loop(self, output_dir, page_count=None):
        """ページをキャプチャし、最終ページ検出または枚数上限で停止する。"""
        self._prepare_output_dir(output_dir)

        page_num = 1
        same_page_streak = 0
        previous_image = None
        started_at = time.monotonic()
        stop_reason = None

        print("途中で止める場合: このターミナルで Ctrl+C、またはマウスを画面左上へ移動。")
        if page_count is None:
            print("最終ページを検出すると自動停止します。")

        try:
            while True:
                if page_count and page_num > page_count:
                    stop_reason = "ページ上限"
                    print(f"指定の {page_count} ページに達したため停止します。")
                    break

                filename = os.path.join(output_dir, f"page_{page_num:04d}.png")
                self._print_progress(page_num, page_count, started_at)
                screenshot = self._screenshot_page(filename)

                # 2ページ目以降: 直前ページと同一なら最終ページ候補
                # 誤検知（めくりアニメ未完了）を避けるため、同一時は追加送りせず再待機のみ
                if previous_image is not None and self._images_are_nearly_identical(
                    previous_image, screenshot
                ):
                    same_page_streak += 1
                    try:
                        os.unlink(filename)
                    except OSError:
                        pass

                    if same_page_streak >= _SAME_PAGE_STREAK_TO_STOP:
                        stop_reason = "最終ページを検出"
                        print(
                            f"\n最終ページを検出したため停止します"
                            f"（連続 {same_page_streak} 回、ページが変わらず）。"
                        )
                        break

                    time.sleep(self.delay_sec)
                    continue

                same_page_streak = 0
                previous_image = screenshot

                if page_count and page_num >= page_count:
                    stop_reason = "ページ上限"
                    print(f"指定の {page_count} ページに達したため停止します。")
                    break

                self._next_page()
                time.sleep(self.delay_sec)
                page_num += 1

        except KeyboardInterrupt:
            stop_reason = "Ctrl+C"
            print("\nCtrl+C によりキャプチャを中断しました。")

        if stop_reason:
            print(f"停止理由: {stop_reason}")
        return stop_reason
    def _prepare_output_dir(self, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            return

        print(f"{output_dir} をクリーンアップしています...")
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"{file_path} の削除に失敗しました: {e}")

    def _find_kindle_window(self):
        """タイトルに Kindle を含むウィンドウを返す。書籍タイトル付きを優先。"""
        seen_handles = set()
        candidates = []

        for title in gw.getAllTitles():
            if not title or "kindle" not in title.lower():
                continue
            for window in gw.getWindowsWithTitle(title):
                if window is None:
                    continue
                handle = getattr(window, "_hWnd", id(window))
                if handle in seen_handles:
                    continue
                seen_handles.add(handle)
                candidates.append(window)

        if not candidates:
            return None

        # より具体的なタイトル（書籍名を含むもの）を優先
        candidates.sort(key=lambda w: len(w.title or ""), reverse=True)
        return candidates[0]
    def _screenshot_page(self, filename):
        """全画面をキャプチャして保存し、PIL Image を返す。"""
        screenshot = pyautogui.screenshot()
        screenshot.save(filename)
        return screenshot

    def _next_page(self):
        if self.direction == "rtl":
            pyautogui.press("left")
        else:
            pyautogui.press("right")

    def _images_are_nearly_identical(self, image_a, image_b):
        """縮小した画像の MSE が閾値以下なら同一とみなす。"""
        a = image_a.convert("RGB").resize(_COMPARE_SIZE, Image.Resampling.BILINEAR)
        b = image_b.convert("RGB").resize(_COMPARE_SIZE, Image.Resampling.BILINEAR)
        diff = ImageChops.difference(a, b)
        histogram = diff.histogram()
        # RGB 各チャンネルの二乗和をピクセル数で割って MSE を近似
        pixel_count = _COMPARE_SIZE[0] * _COMPARE_SIZE[1]
        sum_sq = 0.0
        for channel_offset in (0, 256, 512):
            for value in range(256):
                count = histogram[channel_offset + value]
                sum_sq += (value ** 2) * count
        mse = sum_sq / (pixel_count * 3)
        return mse <= _SAME_PAGE_MSE_THRESHOLD

    def _print_progress(self, page_num, page_count, started_at):
        elapsed_sec = max(0, time.monotonic() - started_at)
        elapsed_text = self._format_duration(elapsed_sec)

        if page_count:
            percent = int((page_num / page_count) * 100)
            # 現在ページ完了までの平均から残りを推定
            if page_num > 1:
                avg_per_page = elapsed_sec / (page_num - 1)
                remaining_sec = avg_per_page * (page_count - page_num + 1)
                eta_text = self._format_duration(remaining_sec)
            else:
                eta_text = "--:--"
            print(
                f"キャプチャ中: {page_num}/{page_count} ({percent}%) "
                f"| 経過 {elapsed_text} | 残り約 {eta_text}"
            )
        else:
            print(
                f"キャプチャ中: {page_num}ページ "
                f"| 経過 {elapsed_text} | 最終ページで自動停止"
            )

    @staticmethod
    def _format_duration(seconds):
        total_seconds = int(seconds)
        return str(timedelta(seconds=total_seconds))
