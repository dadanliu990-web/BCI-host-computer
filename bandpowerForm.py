# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
import numpy as np
import pyqtgraph as pg
from scipy import signal
import os
from lsl_config import FS

qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "curvesform.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)


class BandpowerForm(QtWidgets.QWidget, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowTitle("频段功率")

        # 频段定义
        self.bands = {
            'Delta': (0.5, 4),
            'Theta': (4, 8),
            'Alpha': (8, 13),
            'Beta': (13, 30),
            'Gamma': (30, 45),
        }
        self.band_names = list(self.bands.keys())
        self.band_colors = {
            'Delta': (100, 100, 220),
            'Theta': (0, 180, 180),
            'Alpha': (0, 180, 0),
            'Beta': (220, 150, 0),
            'Gamma': (220, 50, 50),
        }

        # PSD 参数
        self.fs = FS
        self.win_samples = 256
        self.nperseg = 128
        self.noverlap = 64
        self.update_interval_ms = 500
        self.max_buffer_len = 500

        # 显示模式
        self._display_mode = 'absolute'  # 'absolute', 'relative', 'ratio'
        self._channel_mode = 'average'   # 'average' or ch index 0-63
        self._ratio_pair = ('Alpha', 'Beta')

        # 缓存最新 64 通道各频段功率，供 TopoMapForm 共享
        self._cached_band_powers = {}  # {band_name: np.ndarray(64,)}

        # ========== 柱状图 ==========
        self.pw = pg.plot(title="频段功率")
        self.pw.setLabel('bottom', '频段')
        self.pw.setLabel('left', 'Power (dB)')
        self.bar_item = pg.BarGraphItem(x=np.arange(5), height=np.zeros(5), width=0.6)
        self.pw.addItem(self.bar_item)
        self.pw.getPlotItem().getViewBox().setMouseEnabled(x=True, y=True)

        # X 轴标签
        self.pw.getPlotItem().getAxis('bottom').setTicks([[
            (0, 'δ'), (1, 'θ'), (2, 'α'), (3, 'β'), (4, 'γ')
        ]])

        # ========== 数值标签 ==========
        self.value_label = QLabel("δ: --  θ: --  α: --  β: --  γ: --")
        self.value_label.setStyleSheet("font-size: 12px; padding: 4px;")

        # ========== 控制面板 ==========
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        ctrl_layout.addWidget(QLabel("通道:"))
        self.ch_combo = QComboBox()
        self.ch_combo.addItem("全部平均")
        for i in range(64):
            self.ch_combo.addItem(f"Ch{i+1}")
        self.ch_combo.currentIndexChanged.connect(self._on_channel_changed)
        ctrl_layout.addWidget(self.ch_combo)

        ctrl_layout.addWidget(QLabel("模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['absolute', 'relative', 'ratio'])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        ctrl_layout.addWidget(self.mode_combo)

        ctrl_layout.addWidget(QLabel("比值:"))
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItems(['Alpha/Beta', 'Theta/Beta', 'Alpha/Theta', 'Beta/Theta'])
        self.ratio_combo.currentTextChanged.connect(self._on_ratio_changed)
        self.ratio_combo.setVisible(False)
        ctrl_layout.addWidget(self.ratio_combo)

        ctrl_layout.addStretch()

        ctrl_widget = QWidget()
        ctrl_widget.setLayout(ctrl_layout)

        # ========== QSplitter 布局 ==========
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_layout.addWidget(self.pw)
        top_layout.addWidget(self.value_label)
        top_layout.addWidget(ctrl_widget)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_widget)
        splitter.setHandleWidth(3)

        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)
        self.gridLayout.addWidget(splitter, 0, 0)

        # ========== 数据缓冲区 ==========
        self.data_buffer = np.empty(shape=(0, 64))

        # ========== 更新定时器 ==========
        self._timer = QTimer()
        self._timer.timeout.connect(self._update)
        self._timer.start(self.update_interval_ms)

        # ========== QSettings ==========
        self.settings = QSettings('./bandpowerFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(500, 400)))
        pos = self.settings.value("pos")
        size = self.settings.value("size")
        if pos is not None and size is not None:
            screenRect = QApplication.primaryScreen().geometry()
            if pos.x() < screenRect.width() - 100 and pos.y() < screenRect.height() - 100:
                self.move(pos)

    def deal_with_data_inlet(self, ts, arr):
        if arr.shape[1] == 1:
            arr = np.hstack((arr, np.zeros(shape=(arr.shape[0], 63))))
        self.data_buffer = np.concatenate((self.data_buffer, arr), axis=0)
        num_del = self.data_buffer.shape[0] - self.max_buffer_len
        if num_del > 0:
            self.data_buffer = np.delete(self.data_buffer, np.s_[:num_del], axis=0)

    def _compute_bandpower(self, segment):
        f, psd = signal.welch(segment, fs=self.fs, nperseg=self.nperseg, noverlap=self.noverlap, axis=0)
        powers = {}
        for name, (low, high) in self.bands.items():
            mask = (f >= low) & (f < high)
            powers[name] = np.trapz(psd[mask, :], f[mask], axis=0)
        return powers

    def _update(self):
        if self.data_buffer.shape[0] < self.win_samples:
            return

        segment = self.data_buffer[-self.win_samples:, :]

        # 始终计算 64 通道各频段功率并缓存（供 TopoMapForm 共享）
        ch_powers = self._compute_bandpower(segment)  # {band: np.ndarray(64,)}
        self._cached_band_powers = ch_powers

        # 根据通道模式归约到显示值
        if self._channel_mode == 'average':
            powers = {k: np.mean(v) for k, v in ch_powers.items()}
        else:
            powers = {k: float(v[self._channel_mode]) for k, v in ch_powers.items()}

        total = sum(powers.values())

        if self._display_mode == 'absolute':
            heights = [max(powers[n], 1e-12) for n in self.band_names]
            db_heights = [10.0 * np.log10(h) for h in heights]
            self.pw.setLabel('left', 'Power (dB)')
        elif self._display_mode == 'relative':
            if total > 0:
                db_heights = [powers[n] / total * 100 for n in self.band_names]
            else:
                db_heights = [0] * 5
            self.pw.setLabel('left', 'Relative Power (%)')
        else:  # ratio
            num_name, den_name = self._ratio_pair
            num = powers[num_name]
            den = powers[den_name]
            db_heights = [num / max(den, 1e-12)]
            self.bar_item.setOpts(x=np.array([2.0]), height=np.array(db_heights), width=0.6,
                                  brushes=[pg.mkBrush(*self.band_colors['Alpha'])])
            self.value_label.setText(f"{num_name}/{den_name} = {db_heights[0]:.2f}")
            return

        colors = [pg.mkBrush(*self.band_colors[n]) for n in self.band_names]
        self.bar_item.setOpts(x=np.arange(5), height=np.array(db_heights), width=0.6, brushes=colors)

        if self._display_mode == 'absolute':
            self.value_label.setText(
                f"δ: {powers['Delta']:.0f}  θ: {powers['Theta']:.0f}  α: {powers['Alpha']:.0f}  "
                f"β: {powers['Beta']:.0f}  γ: {powers['Gamma']:.0f}  (μV²)"
            )
        else:
            self.value_label.setText(
                f"δ: {powers['Delta']/total*100:.1f}%  θ: {powers['Theta']/total*100:.1f}%  "
                f"α: {powers['Alpha']/total*100:.1f}%  β: {powers['Beta']/total*100:.1f}%  "
                f"γ: {powers['Gamma']/total*100:.1f}%"
            )

    def _on_channel_changed(self, idx):
        if idx == 0:
            self._channel_mode = 'average'
        else:
            self._channel_mode = idx - 1

    def _recreate_bar_item(self, x, height, width=0.6, brushes=None):
        """重建 BarGraphItem —— 柱子数量变化时避免内部 brush 缓存越界"""
        self.pw.removeItem(self.bar_item)
        self.bar_item = pg.BarGraphItem(x=x, height=height, width=width, brushes=brushes)
        self.pw.addItem(self.bar_item)

    def _on_mode_changed(self, mode):
        self._display_mode = mode
        self.ratio_combo.setVisible(mode == 'ratio')
        if mode == 'ratio':
            self._recreate_bar_item(x=np.array([2.0]), height=np.array([0]), width=0.6)
            self.pw.getPlotItem().getAxis('bottom').setTicks([[(2, 'Ratio')]])
        else:
            self._recreate_bar_item(x=np.arange(5), height=np.zeros(5), width=0.6)
            self.pw.getPlotItem().getAxis('bottom').setTicks([[
                (0, 'δ'), (1, 'θ'), (2, 'α'), (3, 'β'), (4, 'γ')
            ]])

    def _on_ratio_changed(self, text):
        parts = text.split('/')
        self._ratio_pair = (parts[0], parts[1])

    def get_band_power(self, band_name):
        """返回指定频段的 64 通道功率数组，供 TopoMapForm 共享；无数据时返回 None"""
        arr = self._cached_band_powers.get(band_name)
        if arr is not None and arr.shape == (64,) and np.all(np.isfinite(arr)):
            return arr
        return None

    def reset_view(self):
        self.pw.autoRange(axis='x')
        self.pw.autoRange(axis='y')
        self.pw.repaint()

    def set_playback_mode(self, active):
        """回放期间暂停内部频段功率定时器，避免重复计算导致卡顿"""
        if active:
            self._timer.stop()
        else:
            self._timer.start(self.update_interval_ms)

    def closeEvent(self, e):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        e.accept()

    def close_win(self):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.close()
