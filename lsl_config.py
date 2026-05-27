# -*- coding: utf-8 -*-
"""
协议配置常量

UDP 常量 —— 用于 WiFi 直连模式（主数据通道）。
  Hardware → WiFi/UDP(port 8080) → UdpReceiver → Controller → UI/Storage
  这是当前架构的主要数据通路，不依赖任何外部进程。

LSL 常量 —— 用于外部程序互联（可选，需主动开启）。
  通过 enable_external_lsl_receive() 可接收其他程序的 LSL 流数据。
  LSL 转发功能已废弃，不再使用。

两个通道互不依赖：UDP 通道始终运行，LSL 通道按需开启。
"""

# ========== UDP 接收参数 ==========
UDP_PORT = 8080
UDP_PACKET_HEADER = 0xAA
UDP_PACKET_FOOTER = 0xEE
UDP_PACKET_SIZE = 262          # 1(AA) + 256(data) + 4(seq) + 1(EE)
UDP_EEG_BYTES = 256            # 中间数据字节数
UDP_SEQ_BYTES = 4              # 序列号字节数
UDP_EEG_CHANNELS = 64          # 每包 EEG 通道数
UDP_EEG_DTYPE = '<i4'          # little-endian int32
UDP_POLL_INTERVAL_MS = 10      # QTimer 轮询间隔（10ms 形成微批处理，250Hz 下每轮收 2-3 包）

# ========== LSL 流定义 ==========
# mi_eeg — 64通道 EEG
LSL_EEG_NAME = 'mi_eeg'
LSL_EEG_TYPE = 'eeg'
LSL_EEG_CHANNELS = 64
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

# ========== 采样率（统一） ==========
FS = 250
