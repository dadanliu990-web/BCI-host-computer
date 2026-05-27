# -*- coding: utf-8 -*-

import numpy as np
import pylsl
import threading
import time

from typing import List

from PyQt5.QtCore import QObject, pyqtSignal

from lsl_config import LSL_EEG_NAME, LSL_ACC_NAME, LSL_HB_NAME


class Inlet:
    """Base class to represent a plottable inlet"""
    def __init__(self, info: pylsl.StreamInfo, processing_flags=None):
        if processing_flags is None:
            processing_flags = pylsl.proc_clocksync | pylsl.proc_dejitter
        self.inlet = pylsl.StreamInlet(info, processing_flags=processing_flags)
        self.name = info.name()
        self.channel_count = info.channel_count()
        self.srate = info.nominal_srate()


class DataInlet(Inlet):
    """A DataInlet represents an inlet with continuous, multi-channel data."""
    dtypes = [[], np.float32, np.float64, None, np.int32, np.int16, np.int8, np.int64]

    def __init__(self, info: pylsl.StreamInfo, s):
        super().__init__(info)
        self.inlet_type = s
        bufsize = (8192, info.channel_count())
        self.buffer = np.empty(bufsize, dtype=self.dtypes[info.channel_format()])

    def pull_data(self):
        _, ts = self.inlet.pull_chunk(timeout=0.0,
                              max_samples=self.buffer.shape[0],
                              dest_obj=self.buffer)
        y = np.empty(shape=(0, 0))
        if not ts:
            return ts, y
        ts = np.asarray(ts)
        y = self.buffer[0:ts.size, :]
        return ts, y


class MarkerInlet(Inlet):
    """A MarkerInlet shows events that happen sporadically as vertical lines"""
    dtypes = [[], np.float32, np.float64, None, np.int32, np.int16, np.int8, np.int64]

    def __init__(self, info: pylsl.StreamInfo, s):
        # 标记流是不规则流(nominal_srate=0)，不应使用 proc_dejitter。
        # dejitter 会缓冲样本以计算时间戳平滑，对于每分钟只有几个标记的流，
        # 缓冲区可能长时间持有标记，在流关闭时丢弃未释放的样本。
        super().__init__(info, processing_flags=pylsl.proc_clocksync)
        self.inlet_type = s
        bufsize = (512, info.channel_count())
        self.buffer = np.empty(bufsize, dtype=self.dtypes[info.channel_format()])

    def pull_data(self):
        _, ts = self.inlet.pull_chunk(timeout=0.0,
                              max_samples=self.buffer.shape[0],
                              dest_obj=self.buffer)
        y = np.empty(shape=(0, 0))
        if not ts:
            return ts, y
        ts = np.asarray(ts)
        y = self.buffer[0:ts.size, :]
        return ts, y


class LSLReceiver(QObject):
    """LSL 流接收器 —— 使用 threading.Thread 替代 QTimer+QThread 确保跨平台可靠运行"""

    evt_lslRcv = pyqtSignal(str, np.ndarray, np.ndarray)

    def __init__(self, wanted_inlets=None):
        super(LSLReceiver, self).__init__()
        self.wanted_inlets = wanted_inlets
        self.inlets: List[Inlet] = []
        self.info_names = []
        self.start_time = pylsl.local_clock()
        self._running = False
        self._thread = None

    def start(self):
        """启动后台拉取线程（50ms 拉取数据，5s 扫描新流）—— 不阻塞调用线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='lsl-receiver')
        self._thread.start()
        print('[LSLReceiver] 后台线程已启动 (pull=50ms, scan=5s)，初始扫描由后台线程执行', flush=True)

    def stop(self):
        """停止后台线程"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        print('[LSLReceiver] 后台线程已停止', flush=True)

    def _run_loop(self):
        """后台线程主循环 —— 不依赖 QTimer，跨平台可靠"""
        last_scan = 0  # 首次迭代立即扫描
        scan_interval = 0.1  # 每 100ms 扫描新流（订阅延迟 ≤100ms，避免错过首标记）
        pull_interval = 0.05  # 每 50ms 拉取数据

        while self._running:
            loop_start = time.time()

            # 1. 拉取数据
            try:
                self._update_impl()
            except Exception as e:
                print(f'[LSLReceiver] update 异常: {e}', flush=True)

            # 2. 周期性扫描新流
            now = time.time()
            if now - last_scan >= scan_interval:
                try:
                    self.get_additional_marker_inlet()
                except Exception as e:
                    print(f'[LSLReceiver] 周期性扫描失败: {e}', flush=True)
                last_scan = now

            # 3. 控制循环速率（补偿执行耗时）
            elapsed = time.time() - loop_start
            sleep_time = max(0, pull_interval - elapsed)
            time.sleep(sleep_time)

    def get_additional_marker_inlet(self):
        """扫描并订阅新的 marker 流（pylsl 线程安全，可从任意线程调用）"""
        new_add_marker_inlets = []
        print(f'[LSLReceiver] 扫描 marker 流...', flush=True)
        try:
            streams = pylsl.resolve_byprop('type', 'Markers', timeout=0.1)
        except TypeError:
            # 兼容旧版 pylsl（不支持 timeout 参数）
            try:
                streams = pylsl.resolve_byprop('type', 'Markers')
            except AttributeError:
                # 兼容更旧版 pylsl（无 resolve_byprop），回退到 resolve_streams
                streams = pylsl.resolve_streams()
        print(f'[LSLReceiver] 发现 {len(streams)} 个 marker 流', flush=True)
        for info in streams:
            print(f'[LSLReceiver]   name="{info.name()}" type="{info.type()}" '
                  f'ch={info.channel_count()} fmt={info.channel_format()} '
                  f'srate={info.nominal_srate()}', flush=True)
            if info.name() in self.info_names:
                print(f'[LSLReceiver]   → 已订阅，跳过', flush=True)
                continue
            if info.type() == 'Markers':
                print(f'[LSLReceiver]   → 添加 marker inlet: {info.name()}', flush=True)
                self.inlets.append(MarkerInlet(info, 'Markers'))
                self.info_names.append(info.name())
                new_add_marker_inlets.append(info.source_id())
            else:
                print(f'[LSLReceiver]   → 非 Marker 流，跳过', flush=True)
        if not new_add_marker_inlets:
            print(f'[LSLReceiver] 本次扫描未发现新的 marker 流', flush=True)
        return new_add_marker_inlets

    def _update_impl(self):
        """拉取所有已订阅 inlet 的数据并通过信号发出"""
        for inlet in self.inlets:
            chunk, ts = inlet.inlet.pull_chunk(timeout=0.0, max_samples=256)

            if not len(ts) > 0:
                continue

            ts = np.asarray(ts)
            y = np.array(chunk)

            if inlet.inlet_type == 'Signals':
                if inlet.name == LSL_EEG_NAME:
                    if y.shape[1] == inlet.channel_count:
                        self.evt_lslRcv.emit(inlet.name, ts, y)
                    else:
                        print(f'[LSLReceiver] EEG 通道数不匹配: {y.shape[1]} vs {inlet.channel_count}', flush=True)

                elif inlet.name == LSL_ACC_NAME:
                    if y.shape[1] == inlet.channel_count:
                        self.evt_lslRcv.emit(inlet.name, ts, y)
                    else:
                        print(f'[LSLReceiver] ACC 通道数不匹配', flush=True)

                elif inlet.name == LSL_HB_NAME:
                    if y.shape[1] == inlet.channel_count:
                        self.evt_lslRcv.emit(inlet.name, ts, y)
                    else:
                        print(f'[LSLReceiver] HB 通道数不匹配', flush=True)

            elif inlet.inlet_type == 'Markers':
                if inlet.name[:13] == 'psycho_marker':
                    self.evt_lslRcv.emit(inlet.name, ts, y)
                    print(f'[LSLReceiver] 收到 marker 数据: {y}', flush=True)
