# -*- coding: utf-8 -*-
"""Single entry point for the serial-to-LSL bridge and the BCI viewer."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from typing import Optional

from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox
import serial.tools.list_ports

from serial_to_lsl_fixed import (
    NOMINAL_SRATE,
    SerialToLSLBridge,
)
from ui import MainWindow


PROJECT_DIR = Path(__file__).resolve().parent


class SingleInstanceLock:
    """Keep a second run.py instance from trying to reuse the serial port."""

    def __init__(self) -> None:
        digest = hashlib.sha256(str(PROJECT_DIR).encode("utf-8")).hexdigest()[:16]
        self.path = Path(tempfile.gettempdir()) / f"bci_viewer_{digest}.lock"
        self.file = None

    def acquire(self) -> bool:
        self.file = self.path.open("a+b")
        try:
            self.file.seek(0, os.SEEK_END)
            if self.file.tell() == 0:
                self.file.write(b"1")
                self.file.flush()
            self.file.seek(0)

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            self.file.close()
            self.file = None
            return False
        return True

    def release(self) -> None:
        if self.file is None:
            return
        try:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the serial-to-LSL bridge and BCI viewer together."
    )
    parser.add_argument("--port", help="Serial port, for example COM6")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--name", default="selfboard_eeg", help="LSL stream name")
    parser.add_argument("--srate", type=int, default=NOMINAL_SRATE)
    parser.add_argument("--uv-per-count", type=float, default=0.001)
    parser.add_argument("--no-checksum", action="store_true")
    parser.add_argument("--print-every", type=int, default=250)
    parser.add_argument(
        "--viewer-only",
        action="store_true",
        help="Start the viewer without opening a serial port",
    )
    return parser.parse_args()


def choose_serial_port(requested_port: Optional[str]) -> Optional[str]:
    if requested_port:
        return requested_port

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    if len(ports) == 1:
        return ports[0].device

    labels = []
    devices = {}
    for port in ports:
        description = port.description or "Serial device"
        label = f"{port.device} — {description}"
        labels.append(label)
        devices[label] = port.device

    selected, accepted = QInputDialog.getItem(
        None,
        "Select EEG serial port",
        "Multiple serial ports were found. Select the EEG acquisition board:",
        labels,
        0,
        False,
    )
    return devices[selected] if accepted else None


def start_bridge(args: argparse.Namespace, port: str) -> SerialToLSLBridge:
    bridge = SerialToLSLBridge(
        port=port,
        baudrate=args.baudrate,
        stream_name=args.name,
        srate=args.srate,
        uv_per_count=args.uv_per_count,
        enable_checksum=not args.no_checksum,
        print_every=args.print_every,
    )
    try:
        bridge.open_serial()
        bridge.start()
    except Exception:
        bridge.stop()
        raise
    return bridge


def main() -> int:
    args = parse_args()

    # Existing INI, log and recorder paths continue to resolve from the project root,
    # regardless of how run.py was launched on another computer.
    os.chdir(PROJECT_DIR)

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")

    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        QMessageBox.information(
            None,
            "BCI Viewer",
            "The application is already running. Close the existing window first.",
        )
        return 1

    bridge = None
    try:
        if not args.viewer_only:
            port = choose_serial_port(args.port)
            if port is None:
                QMessageBox.warning(
                    None,
                    "EEG board not connected",
                    "No serial port was selected. The viewer will start without the "
                    "selfboard_eeg stream.",
                )
            else:
                try:
                    bridge = start_bridge(args, port)
                except Exception as exc:
                    QMessageBox.warning(
                        None,
                        "Cannot open EEG serial port",
                        f"Could not open {port}:\n{exc}\n\n"
                        "Close any old serial-to-LSL process and start run.py again. "
                        "The viewer will continue without the selfboard_eeg stream.",
                    )

        window = MainWindow()
        window.show()
        return app.exec_()
    finally:
        if bridge is not None:
            bridge.stop()
        instance_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
