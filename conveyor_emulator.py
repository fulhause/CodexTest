# -*- coding: utf-8 -*-
"""Simple conveyor emulator communicating via Mitsubishi SLMP (MC protocol).

This module implements an example emulator that connects as a client to a
PLC (server) using the ``pymcprotocol`` library. The emulator simulates a
conveyor driven by an inverter and two work detection sensors.
A small Tkinter GUI is provided to visualise sensor states and control
parameters.

The implementation intentionally keeps the communication layer minimal to
show how SLMP/MC protocol calls can be used. Addresses of PLC devices are
configurable and can be adapted to the target PLC program.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import pymcprotocol
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "pymcprotocol package is required. Install with `pip install pymcprotocol`."
    ) from exc

try:
    import tkinter as tk
    from tkinter import ttk
except Exception as exc:  # pragma: no cover - Tk may not be available
    raise SystemExit("Tkinter is required for the GUI") from exc


@dataclass
class PLCAddresses:
    """Collection of PLC device addresses used by the emulator."""

    start_bit: str = "M0"  # PLC sets ON to start conveyor
    add_work_bit: str = "M2"  # PLC sets ON to add a new work piece
    sensor_bits: List[str] = field(default_factory=lambda: ["M100", "M101"])


class PLCClient:
    """Small wrapper around :class:`pymcprotocol.Type3E`."""

    def __init__(self, host: str, port: int = 5000, plctype: str = "Q") -> None:
        self.host = host
        self.port = port
        self.mc = pymcprotocol.Type3E(plctype)
        self.lock = threading.Lock()
        self.connected = False

    def connect(self) -> None:
        self.mc.connect(self.host, self.port)
        self.connected = True

    def close(self) -> None:
        if self.connected:
            self.mc.close()
            self.connected = False

    def read_bits(self, device: str, size: int) -> List[int]:
        with self.lock:
            return self.mc.batchread_bitunits(device, size)

    def write_bits(self, device: str, values: List[int]) -> None:
        with self.lock:
            self.mc.batchwrite_bitunits(device, values)


@dataclass
class ConveyorEmulator:
    """Simulated conveyor belt with two sensors."""

    plc: PLCClient
    addresses: PLCAddresses = PLCAddresses()
    poll_interval: float = 0.5  # seconds
    speed: float = 0.2  # conveyor speed (relative units per second)
    sensor_pos: List[float] = field(default_factory=lambda: [0.2, 0.8])
    running: bool = False
    works: List[float] = field(default_factory=list)  # positions 0..1
    sensor_states: List[int] = field(default_factory=lambda: [0, 0])

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    # --- Simulation logic -------------------------------------------------
    def _move_works(self, dt: float) -> None:
        if not self.running:
            return
        new_positions = []
        for pos in self.works:
            pos += self.speed * dt
            if pos <= 1.0:
                new_positions.append(pos)
        self.works = new_positions

    def _update_sensors(self) -> None:
        self.sensor_states = [0, 0]
        for pos in self.works:
            for idx, spos in enumerate(self.sensor_pos):
                if abs(pos - spos) < 0.05:
                    self.sensor_states[idx] = 1

    def _poll_plc_commands(self) -> None:
        try:
            cmd_start = self.plc.read_bits(self.addresses.start_bit, 1)[0]
            if cmd_start:
                self.start()
            else:
                self.stop()
            add_work = self.plc.read_bits(self.addresses.add_work_bit, 1)[0]
            if add_work:
                self.works.append(0.0)
        except Exception:
            # communication errors are simply ignored for the demo
            pass

    def _send_sensor_states(self) -> None:
        try:
            for addr, state in zip(self.addresses.sensor_bits, self.sensor_states):
                self.plc.write_bits(addr, [state])
        except Exception:
            pass

    def step(self, dt: float) -> None:
        self._move_works(dt)
        self._update_sensors()
        self._poll_plc_commands()
        self._send_sensor_states()


class ConveyorGUI(tk.Tk):
    def __init__(self, emulator: ConveyorEmulator) -> None:
        super().__init__()
        self.title("Conveyor Emulator")
        self.emu = emulator
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build_widgets()
        self._last_time = time.time()
        self.after(100, self._on_timer)

    def _build_widgets(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Sensor indicators
        self.sensor_vars = [tk.StringVar(value="OFF") for _ in range(2)]
        ttk.Label(frm, text="Sensor 1:").grid(row=0, column=0, sticky="e")
        ttk.Label(frm, textvariable=self.sensor_vars[0]).grid(row=0, column=1)
        ttk.Label(frm, text="Sensor 2:").grid(row=1, column=0, sticky="e")
        ttk.Label(frm, textvariable=self.sensor_vars[1]).grid(row=1, column=1)

        # Add work button
        ttk.Button(frm, text="Add Work", command=self._add_work).grid(
            row=2, column=0, columnspan=2, pady=5
        )

    def _add_work(self) -> None:
        self.emu.works.append(0.0)

    def _on_timer(self) -> None:
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        self.emu.step(dt)
        for var, state in zip(self.sensor_vars, self.emu.sensor_states):
            var.set("ON" if state else "OFF")
        self.after(int(self.emu.poll_interval * 1000), self._on_timer)

    def on_close(self) -> None:
        self.emu.plc.close()
        self.destroy()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Conveyor emulator")
    parser.add_argument("host", help="PLC host address")
    parser.add_argument("--port", type=int, default=5000, help="PLC port")
    args = parser.parse_args()

    plc = PLCClient(args.host, args.port)
    try:
        plc.connect()
    except Exception as exc:
        raise SystemExit(f"Failed to connect PLC: {exc}")

    emu = ConveyorEmulator(plc)
    gui = ConveyorGUI(emu)
    gui.mainloop()


if __name__ == "__main__":
    main()
