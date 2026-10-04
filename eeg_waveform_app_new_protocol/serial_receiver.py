
# -*- coding: utf-8 -*-
"""
串口接收器 —— 通过 USB 虚拟串口（USB转TTL）接收脑电板数据。
解析后通过 Qt 信号发出。

协议格式（22字节）：
  bytes[0:4]   = 包头 AA FF F1 10
  bytes[4:20]  = 数据位 4通道 × 4字节 (int32 LE)
  bytes[20]    = 验证位1：当前包 bytes[0:20] 逐字节累加后取低8位
  bytes[21]    = 验证位2：当前包 bytes[0:20] 双累加校验的第二位

  校验方式：
  verify1 = 0
  verify2 = 0

  for b in bytes[0:20]:
      verify1 = (verify1 + b) & 0xFF
      verify2 = (verify2 + verify1) & 0xFF

  只有 bytes[20] == verify1 且 bytes[21] == verify2 时，
  才认为该数据包有效。
"""

import os
import struct
import numpy as np
import pylsl
import serial

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from lsl_config import (
    SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_PACKET_HEADER_BYTES,
    SERIAL_PACKET_SIZE, SERIAL_EEG_CHANNELS, SERIAL_POLL_INTERVAL_MS,
    LSL_EEG_NAME,
)

def calc_packet_checksum(packet_without_checksum: bytes):
    """
    计算当前数据包的双累加校验。

    参数：
        packet_without_checksum:
            不包含最后两个校验字节的数据。
            对于 22 字节包来说，就是 packet[0:20]。

    返回：
        verify1, verify2

    说明：
        verify1 = 前面所有字节累加后取低8位
        verify2 = 每一步 verify1 再累加后取低8位
    """
    verify1 = 0
    verify2 = 0

    for b in packet_without_checksum:
        verify1 = (verify1 + b) & 0xFF
        verify2 = (verify2 + verify1) & 0xFF

    return verify1, verify2

class SerialReceiver(QObject):
    """串口数据包接收器。

    在 QTimer 回调中轮询串口，解析 4 通道 EEG 数据，
    通过 evt_serial_data 信号发出。
    """

    evt_serial_data = pyqtSignal(str, np.ndarray, np.ndarray)
    # 参数: stream_name (str), timestamps (1D ndarray), data (2D ndarray)

    def __init__(self, port=SERIAL_PORT, baudrate=SERIAL_BAUDRATE, parent=None):
        super().__init__(parent)
        self._port = port
        self._baudrate = baudrate
        self._ser = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.setInterval(SERIAL_POLL_INTERVAL_MS)
        self._packet_count = 0
        self._active = False
        self._buffer = b''       # 串口字节缓冲区
        self._last_heartbeat = 0.0  # 上次心跳日志时间
        self._last_packet_count = 0  # 上次心跳时的包计数

    def start(self):
        if self._active:
            return
        print(f'[SerialReceiver] 正在打开串口 {self._port} (波特率={self._baudrate})...', flush=True)
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=0,           # 非阻塞读
                write_timeout=0,
            )
        except serial.SerialException as e:
            print(f'[SerialReceiver] 无法打开串口 {self._port}: {e}', flush=True)
            # 提供平台相关的诊断建议
            import sys
            if sys.platform.startswith('linux'):
                print(f'[SerialReceiver] 诊断: Linux/WSL2 下请检查:', flush=True)
                print(f'  - 设备是否已连接: ls /dev/tty*', flush=True)
                print(f'  - 当前用户是否在 dialout 组: groups', flush=True)
                print(f'  - 或手动指定端口: export BCI_SERIAL_PORT=/dev/ttyUSB0', flush=True)
                # WSL2 特殊提示
                if 'microsoft' in sys.platform or 'WSL' in os.environ.get('WSL_DISTRO_NAME', ''):
                    print(f'  - WSL2 需通过 usbipd 将 USB 设备挂载到 WSL', flush=True)
            elif sys.platform.startswith('win'):
                print(f'[SerialReceiver] 诊断: Windows 下请检查设备管理器中的串口号', flush=True)
                print(f'  - 或手动指定端口: set BCI_SERIAL_PORT=COM4', flush=True)
            self._ser = None
            return
        print(f'[SerialReceiver] 串口打开成功', flush=True)
        self._buffer = b''
        self._timer.start()
        self._active = True
        print(f'[SerialReceiver] 已启动，监听串口 {self._port}', flush=True)

    def stop(self):
        self._timer.stop()
        if self._ser is not None:
            try:
                self._ser.close()
            except serial.SerialException:
                pass
            self._ser = None
        self._active = False
        print(f'[SerialReceiver] 已停止，共接收 {self._packet_count} 个数据包')

    def _poll(self):
        import time
        if self._ser is None or not self._ser.is_open:
            return

        # 读取串口缓冲区所有可用字节
        try:
            waiting = self._ser.in_waiting
            if waiting > 0:
                self._buffer += self._ser.read(waiting)
        except serial.SerialException:
            return

        # 周期性心跳日志：每 5 秒输出数据速率
        now = time.time()
        if now - self._last_heartbeat >= 5.0:
            rate = (self._packet_count - self._last_packet_count) / (now - self._last_heartbeat)
            if self._packet_count > 0:
                print(f'[SerialReceiver] 数据速率: {rate:.1f} 包/秒 (总包数: {self._packet_count})', flush=True)
            else:
                # 串口已打开但未收到任何数据包
                buf_len = len(self._buffer)
                print(f'[SerialReceiver] 警告: 未收到有效数据包 (缓冲区: {buf_len} 字节)。'
                      f'检查串口连接和硬件。', flush=True)
            self._last_heartbeat = now
            self._last_packet_count = self._packet_count

        # 从缓冲区中提取完整 22 字节数据包
        header = SERIAL_PACKET_HEADER_BYTES
        while len(self._buffer) >= SERIAL_PACKET_SIZE:
            # 查找包头 AA FF F1 10
            idx = self._buffer.find(header)
            if idx < 0:
                # 未找到包头，保留末尾 3 字节（可能是包头片段）
                self._buffer = self._buffer[-3:]
                break
            if idx > 0:
                # 跳过包头之前的垃圾字节
                self._buffer = self._buffer[idx:]

            if len(self._buffer) < SERIAL_PACKET_SIZE:
                break

            packet = self._buffer[:SERIAL_PACKET_SIZE]

            # ==========================================================
            # 校验当前完整数据包
            # bytes[20] 和 bytes[21] 必须全部正确，才接收该包
            # ==========================================================
            expected_verify1, expected_verify2 = calc_packet_checksum(packet[0:20])

            recv_verify1 = packet[20]
            recv_verify2 = packet[21]

            if recv_verify1 != expected_verify1 or recv_verify2 != expected_verify2:
                print(
                    f"[SerialReceiver] 校验失败: "
                    f"recv={recv_verify1:02x} {recv_verify2:02x}, "
                    f"calc={expected_verify1:02x} {expected_verify2:02x}, "
                    f"packet={packet.hex(' ')}",
                    flush=True
                )

                # 跳过 1 字节，重新寻找下一个包头
                self._buffer = self._buffer[1:]
                continue

            # 解析 4 通道数据 int32 little-endian
            eeg_raw = packet[4:20]

            try:
                values = struct.unpack(f'<{SERIAL_EEG_CHANNELS}i', eeg_raw)
            except struct.error:
                self._buffer = self._buffer[1:]
                continue

            arr = np.array(values, dtype=np.float32).reshape(1, SERIAL_EEG_CHANNELS)
            ts = np.array([pylsl.local_clock()], dtype=np.float64)

            self._packet_count += 1
            self.evt_serial_data.emit(LSL_EEG_NAME, ts, arr)

            # 消费已解析的数据包
            self._buffer = self._buffer[SERIAL_PACKET_SIZE:]

    @property
    def packet_count(self):
        return self._packet_count
