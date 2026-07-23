from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from datetime import timedelta
from typing import Protocol, cast

import pyautogui
import pygetwindow as gw
from PIL import Image, ImageChops

from src.types import PageDirection, ResolvedPageDirection

# 直前ページとの MSE がこの値以下なら「同じページ」
_SAME_PAGE_MSE_THRESHOLD = 5.0
# 連射フレーム間の MSE がこの値以下なら「画面が静止した」
_SETTLE_MSE_THRESHOLD = 1.5
# 連射フレーム間の MSE がこの値超なら「めくりアニメーション中」
_MOTION_MSE_THRESHOLD = 8.0
# 静止判定に必要な連続フレーム数（差分が小さい状態が続くこと）
_SETTLE_STREAK_REQUIRED = 4
# 連続して同一ページなら最終ページ到達とみなす
_SAME_PAGE_STREAK_TO_STOP = 2
# 比較用に縮小する一辺のピクセル数
_COMPARE_SIZE = (64, 64)
# 連射キャプチャの間隔
_BURST_POLL_SEC = 0.04
# 全画面案内（F11で終了…）待機
_FULLSCREEN_HINT_POLL_SEC = 0.35
_FULLSCREEN_HINT_TIMEOUT_SEC = 8.0
_FULLSCREEN_HINT_CLEAR_STREAK = 2
_FULLSCREEN_HINT_MIN_WAIT_SEC = 1.5

# Kindle for PC の実行ファイル名（タイトルに kindle-to-pdf 等が含まれる誤検出を避ける）
_KINDLE_PROCESS_NAMES = frozenset({"kindle.exe"})

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SW_RESTORE = 9
_SW_SHOWMAXIMIZED = 3


class _MousePoint(Protocol):
    x: int
    y: int


class _WindowLike(Protocol):
    title: str
    width: int
    height: int


class KindleWindowNotFoundError(Exception):
    """Kindle for PC のウィンドウが見つからない場合。"""


class DirectionDetectError(Exception):
    """ページ送り方向を自動判定できなかった場合。"""


class KindleCapturer:
    def __init__(
        self,
        direction: PageDirection = "auto",
        delay_sec: float = 2.0,
    ) -> None:
        self.direction: PageDirection = direction
        # ページめくり後の静止待ちの最大秒数
        self.delay_sec = delay_sec
        self._cursor_hidden = False
        self._saved_mouse_pos: _MousePoint | None = None
        self._kindle_hwnd: int | None = None
        self._fullscreen_engaged = False
        # マウスを画面左上へ急激に動かすと緊急停止
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0

    def prepare_kindle_window(self) -> None:
        """Kindle ウィンドウを検出し、前面化・最大化・全画面化を試行する。"""
        kindle_window = self._find_kindle_window()
        if kindle_window is None:
            raise KindleWindowNotFoundError(
                "Kindle for PC のウィンドウが見つかりません。"
                "Kindle for PC で本を開いてから再実行してください。"
            )

        hwnd = int(getattr(kindle_window, "_hWnd", 0) or 0)
        self._kindle_hwnd = hwnd if hwnd else None
        print(f"Kindle ウィンドウを検出: {kindle_window.title} (Kindle.exe)")

        if not hwnd or not self._focus_window(hwnd):
            print("ウィンドウの前面化に失敗しました。")
            print("手動で Kindle ウィンドウを前面にしてください。")
        else:
            time.sleep(0.2)
            # 全画面表示を試行（すでに全画面でも害は小さい）
            pyautogui.press("f11")
            self._fullscreen_engaged = True
            time.sleep(0.3)
            print("Kindle ウィンドウを前面化し、全画面化を試行しました。")
            self.wait_for_fullscreen_hint_to_dismiss()

    def exit_fullscreen_if_needed(self) -> None:
        """開始時に全画面化していた場合、F11 で解除する。"""
        if not self._fullscreen_engaged:
            return

        self._restore_cursor()

        hwnd = self._kindle_hwnd
        if not hwnd or not _user32.IsWindow(hwnd):
            kindle_window = self._find_kindle_window()
            hwnd = int(getattr(kindle_window, "_hWnd", 0) or 0) if kindle_window else 0
            self._kindle_hwnd = hwnd or None

        try:
            if hwnd and self._focus_window(hwnd):
                time.sleep(0.15)
                pyautogui.press("f11")
                time.sleep(0.2)
                print("全画面表示を解除しました。")
            else:
                print(
                    "全画面解除のため Kindle を前面にできませんでした。"
                    "必要なら手動で F11 を押してください。"
                )
        except Exception as e:
            print(f"全画面解除に失敗しました: {e}")
        finally:
            self._fullscreen_engaged = False

    def wait_for_fullscreen_hint_to_dismiss(self) -> None:
        """全画面化直後の「F11キーを押して全画面表示を終了」案内が消えるまで待つ。"""
        from src.ocr_namer import has_fullscreen_exit_hint

        print("全画面の案内表示が消えるのを待っています...")
        started_at = time.monotonic()
        deadline = started_at + _FULLSCREEN_HINT_TIMEOUT_SEC
        clear_streak = 0
        saw_hint = False

        while time.monotonic() < deadline:
            screenshot = pyautogui.screenshot()
            top_band = self._crop_top_band(screenshot)

            try:
                hint_visible = has_fullscreen_exit_hint(top_band)
            except Exception as e:
                # OCR 失敗時は上部帯の静止で代替
                print(f"案内表示の OCR に失敗したため、静止判定に切り替えます: {e}")
                self._wait_for_top_band_settle(timeout_sec=max(0.5, deadline - time.monotonic()))
                print("上部画面の静止を確認しました。続行します。")
                return

            if hint_visible:
                if not saw_hint:
                    print("案内表示を検出しました。消去待ち...")
                saw_hint = True
                clear_streak = 0
            else:
                clear_streak += 1
                elapsed = time.monotonic() - started_at
                ready = clear_streak >= _FULLSCREEN_HINT_CLEAR_STREAK and (
                    saw_hint or elapsed >= _FULLSCREEN_HINT_MIN_WAIT_SEC
                )
                if ready:
                    if saw_hint:
                        print("案内表示が消えたことを確認しました。")
                    else:
                        print("案内表示は出ないか、すでに消えているため続行します。")
                    return

            time.sleep(_FULLSCREEN_HINT_POLL_SEC)

        print("案内表示の待機がタイムアウトしたため続行します。")

    @staticmethod
    def _crop_top_band(image: Image.Image) -> Image.Image:
        """案内が出やすい画面上部だけ切り出す。"""
        width, height = image.size
        band_height = max(100, int(height * 0.14))
        return image.crop((0, 0, width, band_height))

    def _wait_for_top_band_settle(self, timeout_sec: float) -> None:
        """上部帯のフレーム差分が小さくなるまで待つ（OCR フォールバック用）。"""
        deadline = time.monotonic() + max(0.2, timeout_sec)
        last = self._to_thumbnail(self._crop_top_band(pyautogui.screenshot()))
        settle_streak = 0

        while time.monotonic() < deadline:
            time.sleep(_BURST_POLL_SEC)
            current = self._to_thumbnail(self._crop_top_band(pyautogui.screenshot()))
            frame_mse = self._mse_thumbs(last, current)
            last = current
            if frame_mse <= _SETTLE_MSE_THRESHOLD:
                settle_streak += 1
                if settle_streak >= _SETTLE_STREAK_REQUIRED:
                    return
            else:
                settle_streak = 0

    def wait_for_focus(self, seconds: int = 2) -> None:
        """キャプチャ開始前の短いカウントダウン。"""
        print("ウィンドウを触らずにそのままお待ちください。")
        for remaining in range(seconds, 0, -1):
            print(f"開始まで {remaining} 秒...")
            time.sleep(1)
        print("キャプチャを開始します。")

    def detect_direction(self) -> ResolvedPageDirection:
        """右キー・左キーを試し、ページが変わる方向を判定する。元のページに戻す。"""
        if self.direction == "ltr":
            print("ページ送り方向: 右送り (ltr)（指定値）")
            return "ltr"
        if self.direction == "rtl":
            print("ページ送り方向: 左送り (rtl)（指定値）")
            return "rtl"

        print("ページ送り方向を自動判定しています...")
        print("※ 本の先頭付近で実行してください（最終ページだと誤判定することがあります）。")

        baseline = pyautogui.screenshot()

        # まず右キー（横書き・ltr で次ページ）
        pyautogui.press("right")
        after_right, changed_right = self._wait_for_settled_page(baseline, self.delay_sec)

        if changed_right:
            pyautogui.press("left")
            self._wait_for_settled_page(after_right, self.delay_sec)
            self.direction = "ltr"
            print("ページ送り方向: 右送り (ltr) と判定しました。")
            return "ltr"

        # 右では変わらない → 左キーを試す（縦書き・rtl）
        pyautogui.press("left")
        after_left, changed_left = self._wait_for_settled_page(baseline, self.delay_sec)

        if changed_left:
            pyautogui.press("right")
            self._wait_for_settled_page(after_left, self.delay_sec)
            self.direction = "rtl"
            print("ページ送り方向: 左送り (rtl) と判定しました。")
            return "rtl"

        raise DirectionDetectError(
            "ページ送り方向を判定できませんでした。"
            "本の先頭付近で開き直すか、--direction ltr または --direction rtl を指定してください。"
        )

    def capture_loop(
        self,
        output_dir: str,
        page_count: int | None = None,
    ) -> str | None:
        """ページをキャプチャし、最終ページ検出または枚数上限で停止する。"""
        self._prepare_output_dir(output_dir)

        page_num = 1
        same_page_streak = 0
        previous_image: Image.Image | None = None
        started_at = time.monotonic()
        stop_reason: str | None = None

        print("途中で止める場合: このターミナルで Ctrl+C。")
        print("（マウスは文字に被らないよう画面右下へ退避し、カーソルを非表示にします）")
        if page_count is None:
            print("最終ページを検出すると自動停止します。")
        print(
            f"静止判定: 連射キャプチャのフレーム差分が十分小さくなるまで待機"
            f"（最大 {self.delay_sec:.2f} 秒/ページ）"
        )

        self._park_and_hide_cursor()
        try:
            while True:
                if page_count and page_num > page_count:
                    stop_reason = "ページ上限"
                    print(f"指定の {page_count} ページに達したため停止します。")
                    break

                filename = os.path.join(output_dir, f"page_{page_num:04d}.png")
                self._print_progress(page_num, page_count, started_at)

                if previous_image is None:
                    # 開始直後も一瞬連射して、表示が落ち着いたフレームを採用
                    screenshot, _ = self._wait_for_settled_page(None, min(self.delay_sec, 0.8))
                    self._save_image(screenshot, filename)
                else:
                    screenshot = previous_image
                    self._save_image(screenshot, filename)

                if page_count and page_num >= page_count:
                    stop_reason = "ページ上限"
                    print(f"指定の {page_count} ページに達したため停止します。")
                    break

                self._next_page()
                next_image, changed = self._wait_for_settled_page(screenshot, self.delay_sec)

                if not changed:
                    same_page_streak = 1
                    while same_page_streak < _SAME_PAGE_STREAK_TO_STOP:
                        next_image, changed = self._wait_for_settled_page(
                            screenshot, self.delay_sec
                        )
                        if changed:
                            break
                        same_page_streak += 1

                    if not changed:
                        stop_reason = "最終ページを検出"
                        print(
                            f"\n最終ページを検出したため停止します"
                            f"（連続 {same_page_streak} 回、静止後もページが変わらず）。"
                        )
                        break

                previous_image = next_image
                page_num += 1

        except KeyboardInterrupt:
            stop_reason = "Ctrl+C"
            print("\nCtrl+C によりキャプチャを中断しました。")
        finally:
            self._restore_cursor()
            self.exit_fullscreen_if_needed()

        if stop_reason:
            print(f"停止理由: {stop_reason}")
        return stop_reason

    def _park_and_hide_cursor(self) -> None:
        """カーソルを画面右下へ退避し、システムカーソルを非表示にする。"""
        try:
            self._saved_mouse_pos = cast(_MousePoint, pyautogui.position())
            screen_width, screen_height = pyautogui.size()
            # 左上は FAILSAFE のため右下へ（端ぴったりだと環境によって問題になることがあるので少し内側）
            pyautogui.moveTo(screen_width - 2, screen_height - 2, duration=0)
        except Exception as e:
            print(f"マウス退避に失敗しました: {e}")

        try:
            # ShowCursor(False) は表示カウンタを減らす。0未満になるまで呼ぶ
            while _user32.ShowCursor(False) >= 0:
                pass
            self._cursor_hidden = True
        except Exception as e:
            print(f"カーソル非表示に失敗しました: {e}")

    def _restore_cursor(self) -> None:
        """カーソル表示とマウス位置を元に戻す。"""
        if self._cursor_hidden:
            try:
                while _user32.ShowCursor(True) < 0:
                    pass
            except Exception:
                pass
            self._cursor_hidden = False

        if self._saved_mouse_pos is not None:
            try:
                pyautogui.moveTo(
                    self._saved_mouse_pos.x,
                    self._saved_mouse_pos.y,
                    duration=0,
                )
            except Exception:
                pass
            self._saved_mouse_pos = None

    def _wait_for_settled_page(
        self,
        previous_image: Image.Image | None,
        timeout_sec: float,
    ) -> tuple[Image.Image, bool]:
        """連射キャプチャし、フレーム間差分（時間微分）が小さく落ち着いた画面を返す。

        Returns:
            (settled_image, changed_from_previous)
            previous_image が None のときは changed は常に True。
        """
        deadline = time.monotonic() + max(0.05, timeout_sec)
        previous_thumb = self._to_thumbnail(previous_image) if previous_image is not None else None

        current: Image.Image = pyautogui.screenshot()
        last_thumb = self._to_thumbnail(current)
        settle_streak = 0
        saw_motion = False

        while time.monotonic() < deadline:
            time.sleep(_BURST_POLL_SEC)
            current = pyautogui.screenshot()
            current_thumb = self._to_thumbnail(current)
            frame_mse = self._mse_thumbs(last_thumb, current_thumb)

            if frame_mse > _MOTION_MSE_THRESHOLD:
                # めくりアニメーション中
                saw_motion = True
                settle_streak = 0
            elif frame_mse <= _SETTLE_MSE_THRESHOLD:
                settle_streak += 1
            else:
                # 中間的な変化（ノイズや遅い描画）
                settle_streak = 0

            last_thumb = current_thumb

            if settle_streak < _SETTLE_STREAK_REQUIRED:
                continue

            # 十分に静止した
            if previous_thumb is None:
                return current, True

            page_mse = self._mse_thumbs(previous_thumb, current_thumb)
            is_new_page = page_mse > _SAME_PAGE_MSE_THRESHOLD

            if is_new_page:
                # 新しいページで静止 → 採用
                return current, True

            if saw_motion:
                # 動いたあと元と同じに戻った／最終ページで動かなかった扱い
                return current, False

            # まだ前ページのまま静止しているだけ（キー入力前〜アニメ開始前）
            # 採用せず、アニメ開始を待ち続ける
            settle_streak = 0

        # タイムアウト: 最後のフレームで判定
        if previous_thumb is None:
            return current, True
        page_mse = self._mse_thumbs(previous_thumb, self._to_thumbnail(current))
        return current, page_mse > _SAME_PAGE_MSE_THRESHOLD

    def _prepare_output_dir(self, output_dir: str) -> None:
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

    def _find_kindle_window(self) -> _WindowLike | None:
        """Kindle.exe のウィンドウを返す（タイトル部分一致による誤検出を避ける）。"""
        seen_handles: set[object] = set()
        candidates: list[_WindowLike] = []

        for title in gw.getAllTitles():
            if not title:
                continue
            for window in gw.getWindowsWithTitle(title):
                if window is None:
                    continue
                handle = getattr(window, "_hWnd", None)
                if handle is None or handle in seen_handles:
                    continue
                seen_handles.add(handle)

                process_name = self._get_process_name(int(handle))
                if process_name not in _KINDLE_PROCESS_NAMES:
                    continue
                candidates.append(cast(_WindowLike, window))

        if not candidates:
            return None

        # 面積が大きい（読書用の本体ウィンドウ）を優先
        def window_area(window: _WindowLike) -> int:
            try:
                return max(0, window.width) * max(0, window.height)
            except Exception:
                return 0

        candidates.sort(key=window_area, reverse=True)
        return candidates[0]

    @staticmethod
    def _focus_window(hwnd: int) -> bool:
        """Win32 API でウィンドウを前面・最大化する。成功なら True。"""
        if not hwnd or not _user32.IsWindow(hwnd):
            return False

        # 最小化なら復元
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, _SW_RESTORE)
            time.sleep(0.2)

        foreground = _user32.GetForegroundWindow()
        current_thread = _kernel32.GetCurrentThreadId()
        foreground_thread = _user32.GetWindowThreadProcessId(foreground, None)
        target_thread = _user32.GetWindowThreadProcessId(hwnd, None)

        attached_fg = False
        attached_target = False
        try:
            if foreground_thread and foreground_thread != current_thread:
                attached_fg = bool(
                    _user32.AttachThreadInput(foreground_thread, current_thread, True)
                )
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    _user32.AttachThreadInput(target_thread, current_thread, True)
                )

            # フォーカス制限を緩和するため Alt を短く叩く
            pyautogui.press("alt")
            time.sleep(0.05)

            _user32.BringWindowToTop(hwnd)
            _user32.ShowWindow(hwnd, _SW_SHOWMAXIMIZED)
            _user32.SetForegroundWindow(hwnd)
            time.sleep(0.2)

            return int(_user32.GetForegroundWindow()) == int(hwnd)
        finally:
            if attached_target:
                _user32.AttachThreadInput(target_thread, current_thread, False)
            if attached_fg:
                _user32.AttachThreadInput(foreground_thread, current_thread, False)

    @staticmethod
    def _get_process_name(hwnd: int) -> str:
        """ウィンドウハンドルから実行ファイル名（小文字）を取得する。"""
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""

        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""

        try:
            buffer = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buffer))
            if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return ""
            return os.path.basename(buffer.value).lower()
        finally:
            _kernel32.CloseHandle(handle)

    def _screenshot_page(self, filename: str) -> Image.Image:
        """全画面をキャプチャして保存し、PIL Image を返す。"""
        screenshot = cast(Image.Image, pyautogui.screenshot())
        self._save_image(screenshot, filename)
        return screenshot

    @staticmethod
    def _save_image(image: Image.Image, filename: str) -> None:
        # compress_level を下げて保存を速くする（品質はロスレスのまま）
        image.save(filename, compress_level=1)

    def _next_page(self) -> None:
        if self.direction == "rtl":
            pyautogui.press("left")
        else:
            pyautogui.press("right")

    @staticmethod
    def _to_thumbnail(image: Image.Image) -> Image.Image:
        return image.convert("RGB").resize(_COMPARE_SIZE, Image.Resampling.BILINEAR)

    @staticmethod
    def _mse_thumbs(thumb_a: Image.Image, thumb_b: Image.Image) -> float:
        """縮小済み RGB 画像同士の平均二乗誤差。"""
        diff = ImageChops.difference(thumb_a, thumb_b)
        histogram = diff.histogram()
        pixel_count = _COMPARE_SIZE[0] * _COMPARE_SIZE[1]
        sum_sq = 0.0
        for channel_offset in (0, 256, 512):
            for value in range(256):
                count = histogram[channel_offset + value]
                sum_sq += (value**2) * count
        return sum_sq / (pixel_count * 3)

    def _images_are_nearly_identical(
        self,
        image_a: Image.Image,
        image_b: Image.Image,
    ) -> bool:
        """縮小した画像の MSE が閾値以下なら同一とみなす。"""
        return (
            self._mse_thumbs(self._to_thumbnail(image_a), self._to_thumbnail(image_b))
            <= _SAME_PAGE_MSE_THRESHOLD
        )

    def _print_progress(
        self,
        page_num: int,
        page_count: int | None,
        started_at: float,
    ) -> None:
        elapsed_sec = max(0.0, time.monotonic() - started_at)
        elapsed_text = self._format_duration(elapsed_sec)

        if page_count:
            percent = int((page_num / page_count) * 100)
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
            pages_per_min = (page_num / elapsed_sec) * 60 if elapsed_sec > 0 and page_num > 1 else 0
            speed_text = f" | 約 {pages_per_min:.0f} ページ/分" if pages_per_min > 0 else ""
            print(
                f"キャプチャ中: {page_num}ページ "
                f"| 経過 {elapsed_text}{speed_text} | 最終ページで自動停止"
            )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = int(seconds)
        return str(timedelta(seconds=total_seconds))
