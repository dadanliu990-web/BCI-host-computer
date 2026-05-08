
# -*- coding: utf-8 -*-
"""
UDP 接收器 —— 集成到主进程，替代独立 udp_bridge.py 脚本。
接收自研脑电板的 WiFi/UDP 数据包，解析后通过 Qt 信号发出。
"""

import socket
import struct
import numpy as np
import pylsl

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from lsl_config import (
    UDP_PORT, UDP_PACKET_HEADER, UDP_PACKET_FOOTER, UDP_PACKET_SIZE,
    UDP_EEG_CHANNELS, UDP_POLL_INTERVAL_MS,
    LSL_EEG_NAME,
)


class UdpReceiver(QObject):
    """UDP 数据包接收器。

    在 QTimer 回调中轮询 socket，解析 64 通道 EEG 数据，
    通过 evt_udp_data 信号发出。
    """

    evt_udp_data = pyqtSignal(str, np.ndarray, np.ndarray)
    # 参数: stream_name (str), timestamps (1D ndarray), data (2D ndarray)

    def __init__(self, port=UDP_PORT, parent=None):
        super().__init__(parent)
        self._port = port
        self._sock = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.setInterval(UDP_POLL_INTERVAL_MS)
        self._packet_count = 0
        self._active = False

    def start(self):
        if self._active:
            return
        print(f'[UdpReceiver] 正在绑定端口 {self._port}...', flush=True)
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(2)  # 防止 bind 在某些网络配置下挂起
            self._sock.bind(('0.0.0.0', self._port))
            self._sock.setblocking(False)
        except OSError as e:
            print(f'[UdpReceiver] 无法绑定端口 {self._port}: {e}', flush=True)
            self._sock = None
            return
        print(f'[UdpReceiver] 端口绑定成功', flush=True)
        self._timer.start()
        self._active = True
        print(f'[UdpReceiver] 已启动，监听端口 {self._port}', flush=True)

    def stop(self):
        self._timer.stop()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._active = False
        print(f'[UdpReceiver] 已停止，共接收 {self._packet_count} 个数据包')

    def _poll(self):
        if self._sock is None:
            return
        # 一次性读空 socket 缓冲区中的所有待处理数据包
        while True:
            try:
                data = self._sock.recv(4096)
            except BlockingIOError:
                break
            except OSError:
                break

            if len(data) != UDP_PACKET_SIZE:
                continue
            if data[0] != UDP_PACKET_HEADER or data[-1] != UDP_PACKET_FOOTER:
                continue

            eeg_raw = data[1:-1]  # 256 字节
            try:
                values = struct.unpack(f'<{UDP_EEG_CHANNELS}i', eeg_raw)
            except struct.error:
                continue

            arr = np.array(values, dtype=np.float32).reshape(1, UDP_EEG_CHANNELS)
            ts = np.array([pylsl.local_clock()], dtype=np.float64)

            self._packet_count += 1
            self.evt_udp_data.emit(LSL_EEG_NAME, ts, arr)

    @property
    def packet_count(self):
        return self._packet_count

