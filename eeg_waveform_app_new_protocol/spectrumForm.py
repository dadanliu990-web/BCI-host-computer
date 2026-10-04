# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLabel, QDoubleSpinBox
import numpy as np
import json
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt
from PyQt5.QtWidgets import QApplication, QWidget

import pyqtgraph as pg
from PyQt5 import QtCore
from scipy import signal
import os
from lsl_config import FS

qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "curvesform.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)

config_file = os.path.join(os.path.dirname(__file__), "ui_config", 'user_config_spectrum_form.json')


class SpectrumForm(QtWidgets.QWidget, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowTitle("Spectrum")

        # ========== 创建频谱显示区域 ==========
        self.pw = pg.plot(title="PSD")
        self.plt = self.pw.getPlotItem()

        vb = self.pw.getPlotItem().getViewBox()
        vb.setMouseEnabled(x=True, y=True)

        self.pw.setLabel('bottom', 'Frequency', 'Hz')
        self.pw.setLabel('left', 'Power', 'dB')
        self.pw.setXRange(0, 60)
        # ====================================

        # ========== PSD 参数 ==========
        self.fs = FS
        # 每次取最近 3 秒数据用于频谱分析
        self.window_sec = 3.0

        # 固定 Welch / FFT 点数为 512 点
        # Fs = 250 Hz 时，512 点对应时间窗约为 512 / 250 = 2.048 s
        self.nperseg_points = 512
        self.update_interval_ms = 100
        self.offset_db = 20.0
        self.max_buffer_secs = 5.0
        # ==============================

        # ========== 创建 4 条曲线 ==========
        self.curves_num = 4
        self.ch_colors = [
            (50, 100, 220),   # Ch1: 蓝
            (50, 180, 50),    # Ch2: 绿
            (220, 50, 50),    # Ch3: 红
            (200, 150, 0),    # Ch4: 橙
        ]
        self.curves = []
        for i in range(self.curves_num):
            pen = pg.mkPen(color=self.ch_colors[i], width=1.2)
            c = self.pw.plot(pen=pen)
            self.curves.append(c)
        # ====================================

        # ========== Ch1-Ch4 CheckBox + 全选/清空 按钮 ==========
        ch_layout = QHBoxLayout()
        ch_layout.setContentsMargins(4, 4, 4, 4)
        ch_layout.setSpacing(6)

        self.checkboxes = []
        for i in range(self.curves_num):
            r, g, b = self.ch_colors[i]
            cb = QCheckBox(f"Ch{i + 1}")
            cb.setStyleSheet(f"color: rgb({r},{g},{b}); font-weight: bold;")
            cb.stateChanged.connect(self.cb_handler)
            self.checkboxes.append(cb)
            ch_layout.addWidget(cb)

        ch_layout.addStretch()

        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedSize(50, 28)
        select_all_btn.clicked.connect(self.select_all_channels)
        ch_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("清空")
        deselect_all_btn.setFixedSize(50, 28)
        deselect_all_btn.clicked.connect(self.deselect_all_channels)
        ch_layout.addWidget(deselect_all_btn)

        ch_widget = QWidget()
        ch_widget.setLayout(ch_layout)
        # =====================================================

        # ========== 手动 Y 轴范围控制 ==========
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        self.fixed_y_checkbox = QCheckBox("固定Y轴范围")
        self.fixed_y_checkbox.setChecked(False)
        self.fixed_y_checkbox.toggled.connect(self._on_fixed_y_toggled)
        ctrl_layout.addWidget(self.fixed_y_checkbox)

        ctrl_layout.addWidget(QLabel("下限:"))
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-200, 2000)
        self.y_min_spin.setValue(-20)
        self.y_min_spin.setSingleStep(5)
        self.y_min_spin.setEnabled(False)
        self.y_min_spin.valueChanged.connect(self._apply_fixed_y_range)
        ctrl_layout.addWidget(self.y_min_spin)

        ctrl_layout.addWidget(QLabel("上限:"))
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-200, 2000)
        self.y_max_spin.setValue(200)
        self.y_max_spin.setSingleStep(5)
        self.y_max_spin.setEnabled(False)
        self.y_max_spin.valueChanged.connect(self._apply_fixed_y_range)
        ctrl_layout.addWidget(self.y_max_spin)

        ctrl_layout.addStretch()
        ctrl_widget = QWidget()
        ctrl_widget.setLayout(ctrl_layout)

        # ========== 垂直布局：频谱 + 通道选择 + Y轴控制 ==========
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)
        main_layout.addWidget(self.pw)
        main_layout.addWidget(ch_widget)
        main_layout.addWidget(ctrl_widget)

        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)

        self.gridLayout.addWidget(main_widget, 0, 0)
        # =====================================================

        # ========== 数据缓冲区 ==========
        self.data_buffer = np.empty(shape=(0, 4))
        self.ts_buffer = np.empty(shape=(0,))
        # ================================

        # ========== PSD 更新定时器 ==========
        self.psd_timer = QtCore.QTimer()
        self.psd_timer.timeout.connect(self._update_psd)
        self.psd_timer.start(self.update_interval_ms)
        # ====================================

        # ========== 加载通道可见性配置 ==========
        if os.path.exists(config_file):
            with open(config_file, 'r') as file:
                self.usr_config_json = json.load(file)
        else:
            self.usr_config_json = {}

        self.show_ch = np.array(self.usr_config_json.get('CH', []))
        if len(self.show_ch) != self.curves_num:
            self.show_ch = np.ones(self.curves_num)
            self.usr_config_json['CH'] = list(self.show_ch)

        for cb in self.checkboxes:
            cb.blockSignals(True)

        for i, ch in enumerate(self.show_ch):
            if i < self.curves_num:
                if ch == 1:
                    self.checkboxes[i].setChecked(True)
                    self.curves[i].show()
                else:
                    self.checkboxes[i].setChecked(False)
                    self.curves[i].hide()

        for cb in self.checkboxes:
            cb.blockSignals(False)
        # ==========================================

        self.settings = QSettings('./spectrumFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(600, 450)))
        if (self.settings.value("pos") is not None) and (self.settings.value("size") is not None):
            screenRect = QApplication.primaryScreen().geometry()
            if self.settings.value("pos").x() < (screenRect.width() - 100) and \
                    self.settings.value("pos").y() < (screenRect.height() - 100):
                self.move(self.settings.value("pos", QPoint(50, 50)))

    def deal_with_data_inlet(self, ts, arr):
        if arr.shape[1] == 1:
            arr = np.hstack((arr, np.zeros(shape=(arr.shape[0], 3))))
        self.data_buffer = np.concatenate((self.data_buffer, arr), axis=0)
        self.ts_buffer = np.concatenate((self.ts_buffer, ts), axis=0)
        t_cutoff = self.ts_buffer[-1] - self.max_buffer_secs
        keep = self.ts_buffer >= t_cutoff
        if not np.all(keep):
            idx = np.argmax(keep)
            self.data_buffer = self.data_buffer[idx:, :]
            self.ts_buffer = self.ts_buffer[idx:]

    def _update_psd(self):
        if self.data_buffer.shape[0] < 2 or self.ts_buffer.shape[0] < 2:
            return

        # 取最近 window_sec 秒数据
        t_cutoff = self.ts_buffer[-1] - self.window_sec
        keep = self.ts_buffer >= t_cutoff

        if keep.sum() < 4:
            return

        segment = self.data_buffer[keep, :]
        segment = segment - np.mean(segment, axis=0, keepdims=True)
        ts_seg = self.ts_buffer[keep]

        # 根据时间戳估计实际采样率
        if len(ts_seg) > 1 and ts_seg[-1] > ts_seg[0]:
            actual_fs = float((len(ts_seg) - 1) / (ts_seg[-1] - ts_seg[0]))
        else:
            actual_fs = self.fs

        # 固定使用 512 点进行 Welch / FFT 频谱分析
        # 注意：这几行一定要放在 for ch 循环之前，而且不要放进 if/else 里面
        actual_nperseg = self.nperseg_points

        # 数据不足 512 点时，不更新频谱
        if len(segment) < actual_nperseg:
            return

        # 50% 重叠
        noverlap = actual_nperseg // 2

        for ch in range(self.curves_num):
            if ch < len(self.show_ch) and self.show_ch[ch]:
                f, psd = signal.welch(
                    segment[:, ch],
                    fs=actual_fs,
                    window='hann',
                    nperseg=actual_nperseg,
                    noverlap=noverlap,
                )

                psd_db = 10.0 * np.log10(np.maximum(psd, 1e-12))
                self.curves[ch].setData(x=f, y=psd_db + self.offset_db * ch)

        if self.fixed_y_checkbox.isChecked():
            self._apply_fixed_y_range()
        else:
            self.pw.enableAutoRange(axis='y')

    def _on_fixed_y_toggled(self, checked):
        self.y_min_spin.setEnabled(checked)
        self.y_max_spin.setEnabled(checked)
        if checked:
            self.pw.disableAutoRange(axis='y')
            self._apply_fixed_y_range()
        else:
            self.pw.enableAutoRange(axis='y')

    def _apply_fixed_y_range(self):
        if self.fixed_y_checkbox.isChecked():
            y_min = self.y_min_spin.value()
            y_max = self.y_max_spin.value()
            if y_max > y_min:
                self.pw.setYRange(y_min, y_max)

    def cb_handler(self):
        for i in range(self.curves_num):
            if self.checkboxes[i].isChecked():
                self.curves[i].show()
                self.show_ch[i] = 1
            else:
                self.show_ch[i] = 0
                self.curves[i].hide()

        self.usr_config_json['CH'] = list(self.show_ch)
        with open(config_file, "w") as outfile:
            json.dump(self.usr_config_json, outfile)

    def select_all_channels(self):
        for i in range(self.curves_num):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(True)

    def deselect_all_channels(self):
        for i in range(self.curves_num):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(False)

    def reset_view(self):
        if self.fixed_y_checkbox.isChecked():
            self._apply_fixed_y_range()
        else:
            self.pw.autoRange(axis='x')
            self.pw.autoRange(axis='y')
        self.pw.repaint()

    def set_playback_mode(self, active):
        if active:
            self.psd_timer.stop()
        else:
            self.psd_timer.start(self.update_interval_ms)

    def closeEvent(self, e):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        e.accept()

    def close_win(self):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.close()
