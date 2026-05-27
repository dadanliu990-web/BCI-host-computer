from PyQt5 import QtCore
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QFileDialog
import threading
import json
import pylsl
import numpy as np

import constantValues as cv
from lslReceiver import LSLReceiver
import debugPrinter as dp

from edfSaver import EDFSaver
from csvSaver import CSVSaver
from dSPx import DSPx
import os

from udp_receiver import UdpReceiver
from data_processor import DataProcessor

usr_config_file = os.path.join(os.path.dirname(__file__), "ui_config", "user_config.json")


class Controller():
    def __init__(self, mainwindow, curForm, specForm=None, impForm=None,
                 bpForm=None, sgForm=None, accForm=None, topoForm=None):
        print('[Controller] __init__ starting...', flush=True)
        self.mw = mainwindow
        self.cf = curForm
        self.sf = specForm
        self.impf = impForm
        self.bpf = bpForm
        self.sgf = sgForm
        self.af = accForm
        self.topo = topoForm
        self._ui_paused = False
        self._impedance_mode = False
        self._alpha_enabled = False
        self._render_frame = 0
        self._render_throttle = 1  # 每5个包推1次 UI → 250/5 = 50Hz 渲染帧率
        self._playback_mode = False
        print('[Controller] creating EDFSaver...', flush=True)
        self.fs = EDFSaver('./data')
        print('[Controller] creating CSVSaver...', flush=True)
        self.csv_saver = CSVSaver('./data')
        self.current_file_name = None

        # LSL 接收器 —— 按需通过 enable_external_lsl_receive() 开启
        self.lslRcv = None

        # DSPx 滤波器 —— 必须在 DataProcessor 之前创建，以便传入
        print('[Controller] creating DSPx...', flush=True)
        self.dsp = DSPx(cv.CH_NUM)
        self.dsp.load_preset('RAW')  # 清除默认滤波（0.3Hz HP + 40Hz LP），与 UI 下拉框 RAW 一致

        # DataProcessor —— 数据处理中心，运行在独立线程
        # 接收 UDP/LSL 原始数据，完成存储缓冲 + 节流 + 分发 + 滤波
        print('[Controller] creating DataProcessor...', flush=True)
        self._data_proc = DataProcessor(
            self.fs, self.csv_saver,
            log_cb=self.mw.log_data,
            render_throttle=self._render_throttle,
            dsp=self.dsp,
        )
        self._data_proc.evt_ui_data.connect(self._on_ui_data)
        self._data_proc_thread = QThread()
        self._data_proc.moveToThread(self._data_proc_thread)
        self._data_proc_thread.start()
        print('[Controller] DataProcessor thread started', flush=True)

        # UDP 接收器 —— 主数据通道，移至独立线程运行
        print('[Controller] creating UdpReceiver...', flush=True)
        self.udp = UdpReceiver()
        self.udp.evt_udp_data.connect(self._data_proc.on_raw_data)
        self._udp_thread = QThread()
        self.udp.moveToThread(self._udp_thread)
        self._udp_thread.started.connect(self.udp.start)
        self._udp_thread.start()
        print('[Controller] UdpReceiver thread started', flush=True)
        self.mw.log_data(f'UDP 接收器已启动，监听端口 {self.udp._port}')

        print('[Controller] loading user_config.json...', flush=True)
        with open(usr_config_file, 'r') as file:
            self.usr_config_json = json.load(file)
        print('[Controller] user_config.json loaded', flush=True)

        self.mw.evt_win.connect(self.win_evt)

        # Alpha 检测 —— 可选加载，文件不存在时静默禁用
        print('[Controller] loading alpha detection...', flush=True)
        try:
            params = np.load("alpha_calibration_params.npz", allow_pickle=True)
            from alpha_detector import AlphaRealtimeDetector, AlphaStateMachine
            from data_aggregator import BlockAggregator

            self.ad = AlphaRealtimeDetector.from_npz(params)
            step_sec = float(params["step"])
            alpha_thr = float(params["alpha_thr"])
            low_thr = float(params["low_thr"])

            self.sm = AlphaStateMachine(
                step_sec=step_sec,
                alpha_thr=alpha_thr,
                low_thr=low_thr,
                hysteresis_ratio=0.05,
                close_min_sec=1.5,
                open_min_sec=1.0,
                artifact_grace_sec=2.0,
                keep_last_on_artifact=True,
            )
            self.aggregator = BlockAggregator(block_size=int(params["step"] * params["fs"]))
            self._alpha_enabled = True
            self.mw.log_info('Alpha 检测模块已加载')
            print('[Controller] alpha detection loaded OK', flush=True)
        except (FileNotFoundError, KeyError, Exception) as e:
            self.ad = None
            self.sm = None
            self.aggregator = None
            self.mw.log_info(f'Alpha 检测模块未加载（文件缺失或无效）: {e}')
            print(f'[Controller] alpha detection skipped: {e}', flush=True)

        print('[Controller] __init__ complete', flush=True)

    def set_highpass(self, freq):
        """设置高通截止频率（Hz），None 则禁用"""
        self.dsp.set_highpass(freq)
        self.mw.log_info(f'高通截止频率: {freq if freq else "Off"}')

    def set_lowpass(self, freq):
        """设置低通截止频率（Hz），None 则禁用"""
        self.dsp.set_lowpass(freq)
        self.mw.log_info(f'低通截止频率: {freq if freq else "Off"}')

    def set_notch(self, freq):
        """设置陷波频率（Hz），None 则禁用"""
        self.dsp.set_notch(freq)
        self.mw.log_info(f'陷波: {freq if freq else "Off"}')

    def stop(self):
        """停止所有接收器线程"""
        if hasattr(self, 'udp') and self.udp is not None:
            self.udp.stop()
        if hasattr(self, '_udp_thread') and self._udp_thread is not None:
            self._udp_thread.quit()
            self._udp_thread.wait(2000)
            self._udp_thread = None
        if self.lslRcv is not None:
            self.lslRcv.stop()
            self.lslRcv = None
        if hasattr(self, '_data_proc_thread') and self._data_proc_thread is not None:
            self._data_proc_thread.quit()
            self._data_proc_thread.wait(2000)
            self._data_proc_thread = None
        print("接收器已停止")

    def pause_data(self):
        """暂停 UI 数据流（断开连接时使用，不停止后台线程/不关闭 socket）"""
        print('[Controller] pause_data — 暂停 UI 数据流', flush=True)
        self._ui_paused = True

    def resume_data(self):
        """恢复 UI 数据流（重新连接时使用）"""
        print('[Controller] resume_data — 恢复 UI 数据流', flush=True)
        self._ui_paused = False
        self._render_frame = 0

    def init_lsl(self, retry=0):
        """初始化 LSL 接收器 —— 使用 threading.Thread 后台拉取，数据发送到 DataProcessor"""
        try:
            self.lslRcv = LSLReceiver()
            self.lslRcv.evt_lslRcv.connect(self._data_proc.on_raw_data)
            self.lslRcv.start()
            self.mw.log_data('LSL 接收器已启动（threading.Thread 模式）')
            print("LSL 接收器初始化成功（threading.Thread）", flush=True)
        except Exception as e:
            self.mw.log_data(f'LSL 初始化失败: {e}')
            print(f"LSL 初始化失败 (尝试 {retry + 1}): {e}", flush=True)
            self.lslRcv = None
            if retry < 20:
                QtCore.QTimer.singleShot(1000, lambda: self.init_lsl(retry + 1))

    def start_impedance_check(self):
        """开始阻抗/信号质量检测 —— 软件模式：从数据缓冲区评估信号质量"""
        self._impedance_mode = True
        if self.impf is not None:
            self.impf._mode = 'signal_quality'
            self.impf.status_label.setText("检测中...")
        self.mw.log_info('阻抗/信号质量检测已开启（软件模式）')

    def stop_impedance_check(self):
        """停止阻抗/信号质量检测"""
        self._impedance_mode = False
        if self.impf is not None:
            self.impf._on_recheck()
        self.mw.log_info('阻抗/信号质量检测已停止')

    def enter_playback_mode(self):
        self._playback_mode = True

    def exit_playback_mode(self):
        self._playback_mode = False

    def enable_external_lsl_receive(self):
        """按需开启外部 LSL 接收 —— 接收来自其他程序的 LSL 流数据。"""
        if self.lslRcv is not None:
            self.mw.log_info('LSL 接收器已在运行中')
            return
        self.init_lsl()

    def _on_ui_data(self, stream_name, ts, arr):
        """主线程 UI 数据分发 —— 仅处理显示，存储和节流已在 DataProcessor 完成"""
        if self._ui_paused or self._playback_mode:
            return

        if stream_name == 'mi_acc':
            self.cf.deal_with_data_acc_inlet(ts, arr)
            if self.af is not None:
                self.af.deal_with_data_inlet(ts, arr)

        elif stream_name == 'mi_eeg_wave':
            self.cf.deal_with_data_inlet(ts, arr)
            # 实时模式下强制 X 轴跟踪最新数据（4 秒窗口）
            if len(ts) > 0:
                latest = ts[-1]
                self.cf.pw.setXRange(max(0, latest - 4), max(latest, 4))

        elif stream_name == 'mi_eeg_spec':
            if self.sf is not None:
                self.sf.deal_with_data_inlet(ts, arr)
            if self.impf is not None:
                self.impf.deal_with_data_inlet(ts, arr)
            if self.bpf is not None:
                self.bpf.deal_with_data_inlet(ts, arr)
            if self.sgf is not None:
                self.sgf.deal_with_data_inlet(ts, arr)
            if self.topo is not None:
                self.topo.deal_with_data_inlet(ts, arr)

        elif stream_name[:13] == 'psycho_marker':
            pass  # 标记由 DataProcessor 直接写入存储，UI 无需处理

    def stim_on_exit(self, s):
        dp.dpt('stim_on_exit')
        self.fs.flush_data()
        # self.csv_saver.flush_data()  # CSV 保存已禁用

    def win_evt(self, s, s2):
        if s == "start_measurement":
            self.start_measurement()
        elif s == "stop_measurement":
            self.stop_measurement()
        elif s == cv.EVT_WIN_QUIT:
            self.stop()
            self.fs.flush_data()
            # self.csv_saver.flush_data()  # CSV 保存已禁用
            with open(usr_config_file, "w") as outfile:
                json.dump(self.usr_config_json, outfile)
            self.cf.close_win()
            dp.dpt("exit ... ")
        elif s == "set_save_path":
            self.save_path = s2
            print(f"保存路径已设置为: {s2}")

    def new_recording(self):
        base_path = getattr(self, 'save_path', './data')
        a = self.fs.get_name()
        b = a.split('/')[-1]
        text, ok = self.mw.get_input_fileName(b)
        if ok and text:
            c = base_path + '/' + text
            if self.fs.make_path(c):
                self.mw.show_error("该文件已存在！")
                return 'f'
            else:
                self.fs.setup(c, text)
                self.csv_saver.setup(c, text)
                if hasattr(self.mw, 'subject_edit'):
                    self.csv_saver.set_metadata('subject_id', self.mw.subject_edit.text())
                if hasattr(self.mw, 'session_edit'):
                    self.csv_saver.set_metadata('session_name', self.mw.session_edit.text())
                if hasattr(self.mw, 'notes_edit'):
                    self.csv_saver.set_metadata('notes', self.mw.notes_edit.text())
                self.current_file_name = self.fs.get_current_name()
                self.mw.log_info(f"保存路径: {c}")
                return 's'
        return 'f'

    def stop_recording(self):
        """异步保存文件 —— 先关闭 save_on 防止竞态写入，再在后台线程中写磁盘"""
        # 原子性关闭写入，阻止 DataProcessor 继续向缓冲区追加数据
        self.fs.save_on = 0
        self.csv_saver.save_on = False

        def _flush():
            self.fs.flush_data()
            # self.csv_saver.flush_data()  # CSV 保存已禁用
        threading.Thread(target=_flush, daemon=True, name='flush-saver').start()

    def start_measurement(self):
        """开始记录 —— 先启动 LSL 接收捕获标记，再创建文件，最后写入暂存标记"""
        # 1. 先启动 LSL，确保 begin 等早期标记不会错过
        self.enable_external_lsl_receive()
        # 2. 再创建文件（可能弹出对话框，期间标记被暂存在 DataProcessor 中）
        if self.new_recording() == 's':
            # 3. 文件就绪（save_on=True），将暂存标记写入存储器
            QtCore.QMetaObject.invokeMethod(
                self._data_proc, 'flush_pending_markers', QtCore.Qt.QueuedConnection
            )
        print("记录已开始", flush=True)

    def insert_manual_marker(self, label):
        """插入手动事件标记到 EDF 和 CSV"""
        ts = np.array([pylsl.local_clock()])
        arr = np.array([label])
        self.fs.new_data('mar', ts, arr)
        self.csv_saver.new_data('mar', ts, arr)

    def stop_measurement(self):
        """停止记录"""
        self.stop_recording()
        # 停止 LSL marker 接收器
        if self.lslRcv is not None:
            self.lslRcv.stop()
            self.lslRcv = None
            print("LSL 接收器已停止", flush=True)
        print("记录已停止，数据已保存")
