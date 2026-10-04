# -*- coding: utf-8 -*-

import numpy as np
import os
import pyedflib
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, QThread


# ============================================================
# 独立文件加载函数 —— 可在后台线程中调用，不依赖 PlaybackController
# ============================================================
FS = 250

def _load_edf_data(filepath):
    """后台线程安全：加载 EDF 文件，返回 (data_eeg, data_ts)"""
    f = pyedflib.EdfReader(filepath)
    n_ch = f.signals_in_file
    n_samples = f.getNSamples()[0]
    data = np.zeros((n_samples, n_ch))
    for i in range(n_ch):
        data[:, i] = f.readSignal(i)
    f.close()
    n_use = min(n_ch, 64)
    data_eeg = data[:, :n_use]
    if n_use < 64:
        pad = np.zeros((n_samples, 64 - n_use))
        data_eeg = np.hstack((data_eeg, pad))
    data_ts = np.arange(n_samples) / FS
    return data_eeg, data_ts


def _load_csv_data(filepath):
    """后台线程安全：加载 CSV 文件，返回 (data_eeg, data_ts)"""
    rows = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('%') or line.startswith('Sample_Index'):
                continue
            if not line:
                continue
            parts = line.split(',')
            try:
                eeg_vals = [float(x) for x in parts[3:3+64]]
                rows.append(eeg_vals)
            except (ValueError, IndexError):
                continue
    if not rows:
        raise ValueError('CSV 文件中无有效 EEG 数据')
    data_eeg = np.array(rows)
    data_ts = np.arange(data_eeg.shape[0]) / FS
    return data_eeg, data_ts


class PlaybackFileLoader(QObject):
    """后台线程 worker：加载回放文件，完成后发射 loaded 信号"""
    loaded = pyqtSignal(object, object)  # data_eeg, data_ts
    error = pyqtSignal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            if self.filepath.lower().endswith('.csv'):
                data_eeg, data_ts = _load_csv_data(self.filepath)
            else:
                data_eeg, data_ts = _load_edf_data(self.filepath)
            self.loaded.emit(data_eeg, data_ts)
        except Exception as e:
            self.error.emit(str(e))


class PlaybackController(QObject):
    """数据回放控制器 —— 一次性加载全部数据，滑块拖动时间轴浏览"""

    playback_finished = pyqtSignal()
    progress_updated = pyqtSignal(int)

    def __init__(self, cf=None, sf=None, impf=None, bpf=None, sgf=None, af=None, topo=None, controller=None):
        super().__init__()
        self.cf = cf
        self.sf = sf
        self.impf = impf
        self.bpf = bpf
        self.sgf = sgf
        self.af = af
        self.topo = topo
        self._ctrl = controller

        self._data_eeg = None     # (N, 64)
        self._data_ts = None      # (N,)
        self._playing = False
        self.fs = FS
        self._speed = 1.0         # 回放速度倍率
        self._window_secs = 4.0   # 默认显示 4 秒窗口
        self._window_samples = int(self._window_secs * self.fs)
        self._saved_max_len = None

        # 自动播放定时器
        self._play_timer = QTimer()
        self._play_timer.timeout.connect(self._advance)

    @staticmethod
    def _clear_form_buffer(form, attr='data_buffer'):
        """清空 Form 的数据缓冲区，同时清空 ts_buffer（如果存在）"""
        if form is not None and hasattr(form, attr):
            setattr(form, attr, np.empty(shape=(0, 64)))
        if form is not None and hasattr(form, 'ts_buffer'):
            form.ts_buffer = np.empty(shape=(0,))

    def set_data(self, data_eeg, data_ts):
        """直接设置回放数据（由外部加载器调用，避免主线程阻塞）"""
        self._data_eeg = data_eeg
        self._data_ts = data_ts

    def load_edf(self, filepath):
        """加载 EDF 文件（主线程同步加载，仅用于兼容旧调用路径）"""
        try:
            self._data_eeg, self._data_ts = _load_edf_data(filepath)
            return True
        except Exception:
            return False

    def load_csv(self, filepath):
        """加载 CSV 文件（主线程同步加载，仅用于兼容旧调用路径）"""
        try:
            self._data_eeg, self._data_ts = _load_csv_data(filepath)
            return True
        except Exception:
            return False

    def play(self):
        """一次性加载全部波形数据并自动滚动播放"""
        if self._data_eeg is None:
            return

        # 进入回放模式，阻断实时数据推送到 UI Form
        if self._ctrl is not None:
            self._ctrl.enter_playback_mode()

        n = self._data_eeg.shape[0]
        t_col = self._data_ts.reshape(-1, 1)
        full_data = np.hstack((t_col, self._data_eeg))

        if self.cf is not None:
            # 保存 max_len 以便 stop 恢复
            self._saved_max_len = self.cf.curve_data_max_len

            # 清空所有 Form 的实时数据缓冲区
            self._clear_form_buffer(self.sf, 'data_buffer')
            self._clear_form_buffer(self.bpf, 'data_buffer')
            self._clear_form_buffer(self.sgf, 'data_buffer')
            self._clear_form_buffer(self.impf, '_data_buffer')
            if self.topo is not None:
                self.topo.reset_view()

            # 加载回放数据到波形窗口
            self.cf.data = full_data
            self.cf.data_acc = np.empty(shape=(0, 5))
            self.cf.curve_data_max_len = n
            self.cf._dirty = True
            self.cf._render()
            self.cf.auto_range_y()

        # 显示第一个窗口，启动自动播放
        self._playing = True
        self._show_window(0.0)
        self._feed_all_forms()
        if self.cf is not None:
            self.cf.pw.repaint()
        self.progress_updated.emit(0)
        self._play_timer.start(40)  # 25fps 自动推进

    def _advance(self):
        """自动播放：每 tick 向前推进一小步"""
        if not self._playing or self._data_eeg is None:
            return
        total = self._data_ts[-1]
        if total <= 0:
            return
        # 获取当前窗口中心时间
        if self.cf is not None:
            x_range = self.cf.pw.viewRange()
            center = (x_range[0][0] + x_range[0][1]) / 2.0
        else:
            center = 0.0
        step = self._speed / 25.0  # 每帧推进 speed/25 秒 → 1x = 实时
        new_center = center + step
        if new_center >= total:
            new_center = total
            self._play_timer.stop()
        fraction = new_center / total
        self._show_window(fraction)
        self.progress_updated.emit(int(fraction * 100))
        self._feed_all_forms()

    def _show_window(self, fraction):
        """设置 plot 的 X 轴范围，显示 fraction 位置附近的时间窗口"""
        if self._data_eeg is None or self.cf is None:
            return
        total_time = self._data_ts[-1]
        win_time = self._window_samples / self.fs
        center = fraction * total_time
        half = win_time / 2.0
        x_min = max(0, center - half)
        x_max = min(total_time, x_min + win_time)
        if x_max - x_min < win_time:
            x_min = max(0, x_max - win_time)
        self.cf.pw.setXRange(x_min, x_max)

    def pause(self):
        """暂停/恢复自动播放"""
        if not self._playing:
            return
        if self._play_timer.isActive():
            self._play_timer.stop()
        else:
            self._play_timer.start(40)

    def stop(self):
        """停止回放，清空所有缓冲区让实时数据立即填充"""
        if not self._playing:
            return
        self._playing = False
        self._play_timer.stop()

        if self.cf is not None:
            # 清空波形缓冲区，新实时数据会从头填充
            self.cf.data = np.empty(shape=(0, 65))
            self.cf.data_acc = np.empty(shape=(0, 5))
            self.cf.curve_data_max_len = self._saved_max_len or 1000
            self.cf._dirty = True
            self.cf._render()
            # 重置 X 轴到默认窗口，重新启用双轴自动范围
            self.cf.pw.setXRange(0, 4)
            self.cf.pw.enableAutoRange(axis='x')
            self.cf.pw.enableAutoRange(axis='y')

        # 清空所有子窗口缓冲区
        self._clear_form_buffer(self.sf, 'data_buffer')
        self._clear_form_buffer(self.bpf, 'data_buffer')
        self._clear_form_buffer(self.sgf, 'data_buffer')
        self._clear_form_buffer(self.impf, '_data_buffer')
        if self.topo is not None:
            self.topo.reset_view()

        # 退出回放模式，恢复实时数据推送
        if self._ctrl is not None:
            self._ctrl.exit_playback_mode()

        self._saved_max_len = None
        self.progress_updated.emit(0)
        self.playback_finished.emit()

    def set_speed(self, speed):
        """speed 控制回放速率和显示窗口宽度"""
        self._speed = speed
        self._window_secs = max(0.5, 4.0 / speed)
        self._window_samples = int(self._window_secs * self.fs)
        if self._playing:
            if self.cf is not None:
                x_range = self.cf.pw.viewRange()
                center = (x_range[0][0] + x_range[0][1]) / 2.0
                total = self._data_ts[-1] if self._data_ts is not None else 1.0
                fraction = center / total if total > 0 else 0
                self._show_window(fraction)

    def seek(self, fraction):
        """拖动滑块 → 移动时间窗口；如果正在自动播放则重置推进起点"""
        if self._data_eeg is None:
            return
        self._show_window(fraction)
        self.progress_updated.emit(int(fraction * 100))
        self._feed_all_forms()
        # 拖动后如果正在播放，自动从新位置继续推进
        if self._playing and not self._play_timer.isActive():
            self._play_timer.start(40)

    def _feed_all_forms(self):
        """将当前可见窗口的 EEG 数据发送到所有子窗口（频谱、频段、时频、拓扑）"""
        if self._data_eeg is None or self.cf is None:
            return
        x_range = self.cf.pw.viewRange()
        t_min, t_max = x_range[0][0], x_range[0][1]
        mask = (self._data_ts >= t_min) & (self._data_ts <= t_max)
        if not np.any(mask):
            return
        ts_chunk = self._data_ts[mask].copy()
        arr_chunk = self._data_eeg[mask, :].copy()
        if ts_chunk.size == 0:
            return
        for form in [self.sf, self.bpf, self.sgf, self.impf, self.topo]:
            if form is not None:
                form.deal_with_data_inlet(ts_chunk, arr_chunk)

    @property
    def duration(self):
        if self._data_ts is None or len(self._data_ts) == 0:
            return 0
        return self._data_ts[-1]
