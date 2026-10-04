# -*- coding: utf-8 -*-
"""
DataProcessor —— 数据处理中心，运行在独立 QThread 中.

接收来自 SerialReceiver / LSLReceiver 的原始数据，在线程内完成：
  1. 存储缓冲（EDF/CSV 写入，预分配数组 O(1) 追加）
  2. 节流控制（波形 vs 频谱使用不同推送频率）
  3. 将显示数据通过跨线程信号发送到主线程 UI

主线程 Controller 仅接收 evt_ui_data 做纯 UI 分发，不再参与 I/O 和计算。

时间轴：使用采样点序号计数器（无硬件序列号），采样率 250Hz。
"""
import threading
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class DataProcessor(QObject):
    """数据处理线程 —— 所有 I/O 和计算均离线执行"""

    # 发送给主线程 Controller 的显示数据 (stream_name, ts, arr)
    evt_ui_data = pyqtSignal(str, np.ndarray, np.ndarray)

    # 外部流名称 → 内部存储简写 的映射
    _STORAGE_NAME_MAP = {
        'mi_eeg': 'eeg',
        'mi_acc': 'acc',
    }

    def __init__(self, edf_saver, csv_saver, log_cb=None, render_throttle=5, dsp=None):
        super().__init__()
        self._fs = edf_saver
        self._csv = csv_saver
        self._log = log_cb if log_cb is not None else (lambda s: None)
        self._render_throttle = render_throttle
        self._render_frame = 0
        self._log_interval = 2.0   # 每 2 秒输出一次硬件数据日志
        self._dsp = dsp  # DSPx 滤波器，None 表示不过滤
        # 录制开始前到达的 marker 暂存于此（解决与文件创建对话框的竞态条件）
        self._pending_markers = []
        self._pending_lock = threading.Lock()
        # 采样点序号计数器（无硬件序列号，使用本地计数器生成理想时间轴）
        self._eeg_sample_index = 0
        self._eeg_first_real_ts = None
        self._acc_sample_index = 0
        # 硬件数据日志时间节流
        self._last_log_time = 0.0

    @staticmethod
    def _is_marker_stream(stream_name):
        """判断是否为 marker 流（通过 LSL 流名称或类型判断）"""
        # 匹配常见 marker 流命名模式
        marker_patterns = ['psycho_marker', 'predict_marker', 'marker', 'Marker', 'Markers']
        return any(stream_name.startswith(p) or stream_name == p for p in marker_patterns)

    @staticmethod
    def _to_storage_name(stream_name):
        """将外部 LSL 流名称映射为存储器的内部简写"""
        if stream_name in DataProcessor._STORAGE_NAME_MAP:
            return DataProcessor._STORAGE_NAME_MAP[stream_name]
        # 所有 marker 类流统一映射为 'mar'
        if DataProcessor._is_marker_stream(stream_name):
            return 'mar'
        return stream_name

    @pyqtSlot()
    def flush_pending_markers(self):
        """录制开始后，将暂存的 marker 写入存储器（在 DataProcessor 线程中执行）"""
        with self._pending_lock:
            if not self._pending_markers:
                return
            pending = self._pending_markers
            self._pending_markers = []
        count = len(pending)
        for stream_name, ts, arr in pending:
            storage_name = self._to_storage_name(stream_name)
            if self._is_marker_stream(stream_name):
                if self._eeg_first_real_ts is not None:
                    ts = np.round((ts - self._eeg_first_real_ts) * 250.0) / 250.0
                    ts = np.maximum(ts, 0.0)
                else:
                    print('[DataProcessor] 警告: 暂存 marker 时无 EEG 参考时间戳', flush=True)
            self._fs.new_data(storage_name, ts, arr)
        if count > 0:
            print(f'[DataProcessor] 已写入 {count} 个暂存 marker', flush=True)

    def on_raw_data(self, stream_name, ts, arr, seq_num=-1):
        """接收原始数据 → 存储 + 节流 + 分发到 UI

        时间轴：使用采样点序号计数器（250Hz），不依赖硬件序列号。
        """
        storage_name = self._to_storage_name(stream_name)

        # === 录制尚未开始时，暂存 marker 以防丢失 ===
        if not self._fs.save_on and storage_name == 'mar':
            with self._pending_lock:
                self._pending_markers.append((stream_name, ts.copy(), arr.copy()))
            print(f'[DataProcessor] 暂存 marker（录制尚未开始）: {stream_name} arr={arr}', flush=True)
            return

        # === 时间戳转换（采样点序号计数器，250Hz）===
        if stream_name == 'mi_eeg':
            n = len(ts)
            if self._eeg_first_real_ts is None:
                self._eeg_first_real_ts = ts[0]
            ts = (self._eeg_sample_index + np.arange(n, dtype=np.float64)) / 250.0
            self._eeg_sample_index += n

        elif stream_name == 'mi_acc':
            n = len(ts)
            ts = (self._acc_sample_index + np.arange(n, dtype=np.float64)) / 250.0
            self._acc_sample_index += n

        elif self._is_marker_stream(stream_name):
            if self._eeg_first_real_ts is not None:
                ts = np.round((ts - self._eeg_first_real_ts) * 250.0) / 250.0
                ts = np.maximum(ts, 0.0)
            else:
                # 尚无 EEG 参考时间戳，使用原始时间戳（后续 flush 时可能被过滤）
                print(f'[DataProcessor] 警告: marker "{stream_name}" 无 EEG 参考时间戳，使用原始值', flush=True)

        # === 存储（使用理想时间戳，全速率写入）===
        self._fs.new_data(storage_name, ts, arr)

        # === UI 分发（按流类型 + 节流策略）===
        if stream_name == 'mi_acc':
            self.evt_ui_data.emit(stream_name, ts, arr)

        elif stream_name == 'mi_eeg':
            self._render_frame += 1
            if self._dsp is not None and arr.ndim == 2 and arr.shape[1] == self._dsp.ch_num:
                ui_arr = self._dsp.filter(arr)
            else:
                ui_arr = arr
            if ts[-1] - self._last_log_time >= self._log_interval:
                self._log(
                    f'已接收 {self._render_frame} 包，'
                    f'ts={ts[0]:.3f}，幅值 [{ui_arr.min():.1f}, {ui_arr.max():.1f}]'
                )
                self._last_log_time = ts[-1]
            # 波形 → 节流
            if self._render_frame % self._render_throttle == 0:
                self.evt_ui_data.emit('mi_eeg_wave', ts, ui_arr)
            # 频谱/分析 → 全速率
            self.evt_ui_data.emit('mi_eeg_spec', ts, ui_arr)

        elif self._is_marker_stream(stream_name):
            self.evt_ui_data.emit(stream_name, ts, arr)
