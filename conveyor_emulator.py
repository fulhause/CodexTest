# -*- coding: utf-8 -*-
"""三菱製PLCとSLMP通信を行うコンベアの簡易エミュレータ。

インバータで駆動するコンベアと2つのワーク検知センサを模擬し、
``pymcprotocol`` を用いてPLCと通信する。Tkinter製のGUIでセンサ状態の
表示やワーク投入を行える。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import pymcprotocol
except ImportError as exc:  # pragma: no cover - 実行時に処理される
    raise SystemExit(
        "pymcprotocol パッケージが必要です。`pip install pymcprotocol` でインストールしてください。"
    ) from exc

try:
    import tkinter as tk
    from tkinter import ttk
except Exception as exc:  # pragma: no cover - Tk が利用できない場合
    raise SystemExit("GUIには Tkinter が必要です") from exc


@dataclass
class PLCアドレス:
    """エミュレータで使用するPLCデバイスのアドレス群。"""

    開始ビット: str = "M0"  # PLCがONにするとコンベア開始
    ワーク追加ビット: str = "M2"  # PLCがONにするとワーク追加
    センサビット群: List[str] = field(default_factory=lambda: ["M100", "M101"])


class PLCクライアント:
    """ :class:`pymcprotocol.Type3E` をラップする簡易クラス。"""

    def __init__(self, ホスト: str, ポート: int = 5000, PLC種別: str = "Q") -> None:
        self.ホスト = ホスト
        self.ポート = ポート
        self.通信 = pymcprotocol.Type3E(PLC種別)
        self.ロック = threading.Lock()
        self.接続済み = False

    def 接続(self) -> None:
        self.通信.connect(self.ホスト, self.ポート)
        self.接続済み = True

    def 切断(self) -> None:
        if self.接続済み:
            self.通信.close()
            self.接続済み = False

    def ビット読み込み(self, デバイス: str, サイズ: int) -> List[int]:
        with self.ロック:
            return self.通信.batchread_bitunits(デバイス, サイズ)

    def ビット書き込み(self, デバイス: str, 値: List[int]) -> None:
        with self.ロック:
            self.通信.batchwrite_bitunits(デバイス, 値)


@dataclass
class コンベアエミュレータ:
    """2つのセンサを備えたコンベアのシミュレーション。"""

    PLC: PLCクライアント
    アドレス: PLCアドレス = PLCアドレス()
    ポーリング間隔: float = 0.5  # 秒
    速度: float = 0.2  # コンベア速度（相対単位/秒）
    センサ位置: List[float] = field(default_factory=lambda: [0.2, 0.8])
    稼働中: bool = False
    ワーク位置リスト: List[float] = field(default_factory=list)  # 位置 0..1
    センサ状態: List[int] = field(default_factory=lambda: [0, 0])

    def 開始(self) -> None:
        self.稼働中 = True

    def 停止(self) -> None:
        self.稼働中 = False

    # --- シミュレーション処理 ---------------------------------------------
    def _ワーク移動(self, 経過時間: float) -> None:
        if not self.稼働中:
            return
        新位置 = []
        for 位置 in self.ワーク位置リスト:
            位置 += self.速度 * 経過時間
            if 位置 <= 1.0:
                新位置.append(位置)
        self.ワーク位置リスト = 新位置

    def _センサ更新(self) -> None:
        self.センサ状態 = [0, 0]
        for 位置 in self.ワーク位置リスト:
            for 番号, センサ位置 in enumerate(self.センサ位置):
                if abs(位置 - センサ位置) < 0.05:
                    self.センサ状態[番号] = 1

    def _PLCコマンド取得(self) -> None:
        try:
            cmd_start = self.PLC.ビット読み込み(self.アドレス.開始ビット, 1)[0]
            if cmd_start:
                self.開始()
            else:
                self.停止()
            add_work = self.PLC.ビット読み込み(self.アドレス.ワーク追加ビット, 1)[0]
            if add_work:
                self.ワーク位置リスト.append(0.0)
        except Exception:
            # 通信エラーはデモなので無視する
            pass

    def _センサ状態送信(self) -> None:
        try:
            for addr, state in zip(self.アドレス.センサビット群, self.センサ状態):
                self.PLC.ビット書き込み(addr, [state])
        except Exception:
            pass

    def ステップ(self, 経過時間: float) -> None:
        self._ワーク移動(経過時間)
        self._センサ更新()
        self._PLCコマンド取得()
        self._センサ状態送信()


class コンベアGUI(tk.Tk):
    def __init__(self, エミュレータ: コンベアエミュレータ) -> None:
        super().__init__()
        self.title("コンベアエミュレータ")
        self.エミュレータ = エミュレータ
        self.protocol("WM_DELETE_WINDOW", self.閉じる)
        self._ウィジェット作成()
        self._前回時刻 = time.time()
        self.after(100, self._タイマー処理)

    def _ウィジェット作成(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # センサ表示
        self.センサ変数 = [tk.StringVar(value="OFF") for _ in range(2)]
        ttk.Label(frm, text="センサ1:").grid(row=0, column=0, sticky="e")
        ttk.Label(frm, textvariable=self.センサ変数[0]).grid(row=0, column=1)
        ttk.Label(frm, text="センサ2:").grid(row=1, column=0, sticky="e")
        ttk.Label(frm, textvariable=self.センサ変数[1]).grid(row=1, column=1)

        # ワーク追加ボタン
        ttk.Button(frm, text="ワーク追加", command=self._ワーク追加).grid(
            row=2, column=0, columnspan=2, pady=5
        )

    def _ワーク追加(self) -> None:
        self.エミュレータ.ワーク位置リスト.append(0.0)

    def _タイマー処理(self) -> None:
        now = time.time()
        経過 = now - self._前回時刻
        self._前回時刻 = now
        self.エミュレータ.ステップ(経過)
        for var, state in zip(self.センサ変数, self.エミュレータ.センサ状態):
            var.set("ON" if state else "OFF")
        self.after(int(self.エミュレータ.ポーリング間隔 * 1000), self._タイマー処理)

    def 閉じる(self) -> None:
        self.エミュレータ.PLC.切断()
        self.destroy()


def メイン() -> None:
    import argparse

    パーサ = argparse.ArgumentParser(description="コンベアエミュレータ")
    パーサ.add_argument("host", help="PLCのホストアドレス")
    パーサ.add_argument("--port", type=int, default=5000, help="PLCのポート番号")
    引数 = パーサ.parse_args()

    plc = PLCクライアント(引数.host, 引数.port)
    try:
        plc.接続()
    except Exception as exc:
        raise SystemExit(f"PLCへの接続に失敗しました: {exc}")

    emu = コンベアエミュレータ(plc)
    gui = コンベアGUI(emu)
    gui.mainloop()


if __name__ == "__main__":
    メイン()
