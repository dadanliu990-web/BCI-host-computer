# -*- coding: utf-8 -*-
"""
DataProcessor —— 数据处理中心，运行在独立 QThread 中.

接收来自 UdpReceiver / LSLReceiver 的原始数据，在线程内完成：
  1. 存储缓冲（EDF/CSV 写入，预分配数组 O(1) 追加）
  2. 节流控制（波形 vs 频谱使用不同推送频率）
  3. 将显示数据通过跨线程信号发送到主线程 UI

主线程 Controller 仅接收 evt_ui_data 做纯 UI 分发，不再参与 I/O 和计算。
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
        # 硬件序列号时间轴（UDP 模式，seq_num >= 0）
        self._base_seq = None         # 第一个包的序列号，理想时间 = (seq - base_seq) / 250
        self._prev_seq = -1           # 上一个包的序列号（用于丢包检测）
        self._lost_packets = 0         # 累计丢失包数
        self._loss_window_seq = 0      # 丢包窗口起始 seq
        self._loss_log_interval = 250  # 每 250 包（约 1 秒）报告一次丢包率
        self._seq_ts_ring = []         # 环形缓冲区: [(seq, real_ts), ...] 用于 marker 对齐
        self._seq_ring_max = 500       # 保留最近 500 个映射（2 秒 @ 250Hz）
        # LSL 模式的回退（seq_num < 0 时使用）
        self._eeg_sample_index = 0
        self._eeg_first_real_ts = None
        self._acc_sample_index = 0
        # 硬件数据日志时间节流
        self._last_log_time = 0.0

    @staticmethod
    def _to_storage_name(stream_name):
        """将外部 LSL 流名称映射为存储器的内部简写"""
        # 精确匹配
        if stream_name in DataProcessor._STORAGE_NAME_MAP:
            return DataProcessor._STORAGE_NAME_MAP[stream_name]
        # psycho_marker / predict_marker 等 → 'mar'
        if stream_name.startswith('psycho_marker') or stream_name.startswith('predict_marker'):
            return 'mar'
        # 未知流名称原样返回（不会匹配任何 saver 分支，静默忽略）
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
            # 转换 marker 时间戳为理想时间
            if stream_name[:13] == 'psycho_marker':
                if len(self._seq_ts_ring) > 0:
                    # UDP 模式：根据 LSL 时间戳找到最接近的 seq
                    marker_ts_0 = ts[0]
                    best_seq = self._seq_ts_ring[0][0]
                    best_dist = abs(self._seq_ts_ring[0][1] - marker_ts_0)
                    for s, rts in self._seq_ts_ring:
                        dist = abs(rts - marker_ts_0)
                        if dist < best_dist:
                            best_dist = dist
                            best_seq = s
                    ts = np.array([(best_seq - self._base_seq) / 250.0])
                elif self._eeg_first_real_ts is not None:
                    ts = np.round((ts - self._eeg_first_real_ts) * 250.0) / 250.0
                    ts = np.maximum(ts, 0.0)
                else:
                    # 尚无 EEG 数据参考，暂存原始时间戳，由 flush_data 阶段兜底过滤
                    print('[DataProcessor] 警告: 暂存 marker 时无 EEG 参考时间戳', flush=True)
            self._fs.new_data(storage_name, ts, arr)
            # self._csv.new_data(storage_name, ts, arr)  # CSV 保存已禁用
        if count > 0:
            print(f'[DataProcessor] 已写入 {count} 个暂存 marker', flush=True)

    def on_raw_data(self, stream_name, ts, arr, seq_num=-1):
        """接收原始数据 → 存储 + 节流 + 分发到 UI

        UDP 信号: evt_udp_data(str, ndarray, ndarray, int)    → seq_num 由硬件提供
        LSL 信号: evt_lslRcv(str, ndarray, ndarray)           → seq_num=-1 (回退模式)
        """
        storage_name = self._to_storage_name(stream_name)

        # === 录制尚未开始时，暂存 marker 以防丢失（竞态条件：LSL 先启动、文件后创建）===
        if not self._fs.save_on and storage_name == 'mar':
            with self._pending_lock:
                self._pending_markers.append((stream_name, ts.copy(), arr.copy()))
            print(f'[DataProcessor] 暂存 marker（录制尚未开始）: {stream_name} arr={arr}', flush=True)
            return

        # === 丢包率统计（UDP 模式：基于硬件序列号精确计算）===
        if stream_name == 'mi_eeg' and seq_num >= 0:
            if self._base_seq is None:
                self._base_seq = seq_num
                self._loss_window_seq = seq_num
            if self._prev_seq >= 0:
                gap = seq_num - self._prev_seq - 1
                if gap < 0:
                    gap += 0x100000000  # uint32 回绕修正
                self._lost_packets += gap
            self._prev_seq = seq_num
            # 每 250 包检查一次丢包率
            window_pkts = seq_num - self._loss_window_seq
            if window_pkts >= self._loss_log_interval:
                loss_pct = self._lost_packets / window_pkts * 100.0
                if loss_pct > 5.0:
                    self._log(
                        f'[丢包警告] 窗口={window_pkts}包, 丢失={self._lost_packets}包, '
                        f'丢包率={loss_pct:.1f}%'
                    )
                self._lost_packets = 0
                self._loss_window_seq = seq_num

        # === 时间戳转换 ===
        if stream_name == 'mi_eeg':
            n = len(ts)
            if seq_num >= 0:
                # UDP 模式：理想时间 = (seq - base_seq) / 250
                ideal_ts = (seq_num - self._base_seq + np.arange(n, dtype=np.float64)) / 250.0
                # 存储 (seq, real_ts) 映射，供 marker 对齐
                self._seq_ts_ring.append((seq_num, ts[0]))
                if len(self._seq_ts_ring) > self._seq_ring_max:
                    self._seq_ts_ring.pop(0)
                ts = ideal_ts
            else:
                # LSL 模式：采样点序号计数器
                if self._eeg_first_real_ts is None:
                    self._eeg_first_real_ts = ts[0]
                ts = (self._eeg_sample_index + np.arange(n, dtype=np.float64)) / 250.0
                self._eeg_sample_index += n

        elif stream_name == 'mi_acc':
            n = len(ts)
            ts = (self._acc_sample_index + np.arange(n, dtype=np.float64)) / 250.0
            self._acc_sample_index += n

        elif stream_name[:13] == 'psycho_marker':
            if len(self._seq_ts_ring) > 0:
                # 有 seq 映射（UDP 模式）：逐个 marker 根据 LSL 时间戳找到最接近的 seq
                n_markers = len(ts)
                new_ts = np.empty(n_markers)
                for i in range(n_markers):
                    marker_ts = ts[i]
                    best_seq = self._seq_ts_ring[0][0]
                    best_dist = abs(self._seq_ts_ring[0][1] - marker_ts)
                    for s, rts in self._seq_ts_ring:
                        dist = abs(rts - marker_ts)
                        if dist < best_dist:
                            best_dist = dist
                            best_seq = s
                    new_ts[i] = (best_seq - self._base_seq) / 250.0
                ts = new_ts
            elif self._eeg_first_real_ts is not None:
                # LSL 模式：用第一个 EEG 时间戳对齐
                ts = np.round((ts - self._eeg_first_real_ts) * 250.0) / 250.0
                ts = np.maximum(ts, 0.0)

        # === 存储（使用理想时间戳，全速率写入）===
        self._fs.new_data(storage_name, ts, arr)
        # self._csv.new_data(storage_name, ts, arr)  # CSV 保存已禁用

        # === UI 分发（按流类型 + 节流策略）===
        if stream_name == 'mi_acc':
            self.evt_ui_data.emit(stream_name, ts, arr)

        elif stream_name == 'mi_eeg':
            self._render_frame += 1
            # 滤波 —— 存储用原始数据，UI 用滤波后数据
            if self._dsp is not None and arr.ndim == 2 and arr.shape[1] == self._dsp.ch_num:
                ui_arr = self._dsp.filter(arr)
            else:
                ui_arr = arr
            if ts[-1] - self._last_log_time >= self._log_interval:
                if seq_num >= 0:
                    self._log(
                        f'已接收 {self._render_frame} 包 (seq={seq_num})，'
                        f'ts={ts[0]:.3f}，幅值 [{ui_arr.min():.1f}, {ui_arr.max():.1f}]'
                    )
                else:
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

        elif stream_name[:13] == 'psycho_marker':
            self.evt_ui_data.emit(stream_name, ts, arr)
