# -*- coding: utf-8 -*-
"""
协议配置常量

串口常量 —— 用于 USB 虚拟串口（USB转TTL）直连模式（主数据通道）。
  Hardware → USB/Serial → SerialReceiver → Controller → UI/Storage
  这是当前架构的主要数据通路，不依赖任何外部进程。

LSL 常量 —— 用于外部程序互联（可选，需主动开启）。
  通过 enable_external_lsl_receive() 可接收其他程序的 LSL 流数据。
  LSL 转发功能已废弃，不再使用。

两个通道互不依赖：串口通道始终运行，LSL 通道按需开启。
"""

import os
import sys
import glob


def _detect_serial_port():
    """
    自动检测串口设备路径。

    优先级:
      1. 环境变量 BCI_SERIAL_PORT（手动指定）
      2. Linux/WSL2: 扫描 /dev/ttyUSB*, /dev/ttyACM*, /dev/ttyS*
      3. Windows: 扫描 COM1-COM16
      4. 回退到默认值

    返回:
        str: 检测到的串口路径，如果未找到则返回默认值
    """
    # 1. 环境变量覆盖
    env_port = os.environ.get('BCI_SERIAL_PORT')
    if env_port:
        print(f'[lsl_config] 使用环境变量 BCI_SERIAL_PORT={env_port}', flush=True)
        return env_port

    # 2. Linux/WSL2 自动检测
    if sys.platform.startswith('linux'):
        patterns = ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/ttyS*']
        for pattern in patterns:
            matches = sorted(glob.glob(pattern))
            if matches:
                port = matches[0]
                print(f'[lsl_config] Linux 自动检测到串口: {port}', flush=True)
                return port
        print('[lsl_config] Linux 未检测到串口设备，使用默认值 /dev/ttyUSB0', flush=True)
        return '/dev/ttyUSB0'

    # 3. Windows 自动检测 (使用 serial.tools.list_ports)
    if sys.platform.startswith('win'):
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            if ports:
                # 优先选择 USB 串口设备
                for p in ports:
                    if 'USB' in p.description.upper() or 'SERIAL' in p.description.upper():
                        print(f'[lsl_config] Windows 自动检测到 USB 串口: {p.device} ({p.description})', flush=True)
                        return p.device
                # 回退到第一个可用串口
                port = ports[0].device
                print(f'[lsl_config] Windows 自动检测到串口: {port} ({ports[0].description})', flush=True)
                return port
        except ImportError:
            print('[lsl_config] pyserial 未安装 list_ports 支持，使用默认 COM4', flush=True)

    # 4. 回退默认值
    return 'COM4'


# ========== 串口接收参数 ==========
SERIAL_PORT = _detect_serial_port()           # 自动检测串口路径
SERIAL_BAUDRATE = 115200       # 波特率
SERIAL_PACKET_HEADER_BYTES = bytes([0xAA, 0xFF, 0xF1, 0x10])  # 4字节包头
SERIAL_PACKET_SIZE = 22        # 4(header) + 16(data 4ch×4B) + 2(verify)
SERIAL_EEG_BYTES = 16          # 中间数据字节数（4通道 × 4字节）
SERIAL_EEG_CHANNELS = 4        # 每包 EEG 通道数
SERIAL_EEG_DTYPE = '<i4'       # little-endian int32
SERIAL_VERIFY_BYTE1_OFFSET = 20  # 验证位1：bytes[0:20]的sum取低8位
SERIAL_VERIFY_BYTE2_OFFSET = 21  # 验证位2：每次byte20累加后取低8位
SERIAL_POLL_INTERVAL_MS = 5    # QTimer 轮询间隔（5ms，250Hz 下每轮收 1-2 包）

# ========== LSL 流定义 ==========
# mi_eeg — 4通道 EEG
LSL_EEG_NAME = 'mi_eeg'
LSL_EEG_TYPE = 'eeg'
LSL_EEG_CHANNELS = 4
LSL_EEG_SRATE = 250
LSL_EEG_FORMAT = 'float32'
LSL_EEG_SOURCE_PREFIX = 'mi'

# mi_acc — 4通道 加速度计
LSL_ACC_NAME = 'mi_acc'
LSL_ACC_TYPE = 'acc'
LSL_ACC_CHANNELS = 4
LSL_ACC_SRATE = 250
LSL_ACC_FORMAT = 'float32'
LSL_ACC_SOURCE_PREFIX = 'mi'

# hb_eeg — 1通道 头带EEG
LSL_HB_NAME = 'hb_eeg'
LSL_HB_TYPE = 'eeg'
LSL_HB_CHANNELS = 1
LSL_HB_SRATE = 250
LSL_HB_FORMAT = 'float32'
LSL_HB_SOURCE_PREFIX = 'hb'

# ========== UDP 接收参数（WiFi 模式）==========
UDP_PORT = 1238                  # UDP 监听端口
UDP_PACKET_HEADER_BYTES = bytes([0xAA, 0xFF, 0xF1, 0x10])  # 4字节包头（与串口相同）
UDP_PACKET_SIZE = 22             # 4(header) + 16(data 4ch×4B) + 2(verify)
UDP_EEG_CHANNELS = 4             # 每包 EEG 通道数
UDP_POLL_INTERVAL_MS = 1         # QTimer 轮询间隔（1ms，UDP 高频数据）

# ========== 采样率（统一） ==========
FS = 250
