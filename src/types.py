"""プロジェクト共通の型定義。"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# ページ送り方向（CLI / キャプチャ設定）
PageDirection = Literal["auto", "ltr", "rtl"]
ResolvedPageDirection = Literal["ltr", "rtl"]


class OcrLine(TypedDict, total=False):
    """winocr が返す行オブジェクト。"""

    text: str


class OcrResult(TypedDict, total=False):
    """winocr.recognize_pil_sync が返す辞書。

    実装・言語によってキーの有無が変わるため NotRequired で表現する。
    """

    text: NotRequired[str]
    lines: NotRequired[list[OcrLine]]


class CaptureProgress(TypedDict):
    """キャプチャ進捗表示用のスナップショット。"""

    page_num: int
    page_count: int | None
    elapsed_sec: float


class SplitJob(TypedDict):
    """PDF 分割ジョブの入力。"""

    input_path: str
    chunk_size: int
    output_dir: NotRequired[str | None]
