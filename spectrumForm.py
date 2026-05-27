# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLabel, QDoubleSpinBox
import numpy as np
import json
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt
from PyQt5.QtWidgets import QApplication, QScrollArea, QGridLayout, QWidget, QVBoxLayout, QHBoxLayout

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
        self.window_sec = 3.0          # 时间窗口（秒）
        self.nperseg_sec = 3.0        # welch 每段时长（秒）
        self.update_interval_ms = 200  # 5 Hz 刷新
        self.offset_db = 20.0
        self.max_buffer_secs = 5.0     # 缓冲区最大时长（秒）
        # ==============================

        # ========== 创建 64 条曲线 ==========
        self.curves_num = 64
        self.curves = []
        for i in range(self.curves_num):
            c = self.pw.plot()
            self.curves.append(c)
        # ====================================

        # ========== 芯片按钮区域 ==========
        button_main_layout = QHBoxLayout()
        button_main_layout.setContentsMargins(0, 0, 0, 0)

        chip_buttons_layout = QHBoxLayout()
        chip_buttons_layout.setSpacing(5)

        for chip in range(8):
            btn = QPushButton(f"芯片{chip + 1}")
            btn.setToolTip(f"Ch{chip * 8 + 1}-{chip * 8 + 8}")
            btn.setFixedSize(60, 30)
            btn.clicked.connect(lambda checked, c=chip: self.select_chip(c))
            chip_buttons_layout.addWidget(btn)

        right_buttons_layout = QHBoxLayout()
        right_buttons_layout.setSpacing(5)

        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedSize(50, 30)
        select_all_btn.clicked.connect(self.select_all_channels)
        deselect_all_btn = QPushButton("清空")
        deselect_all_btn.setFixedSize(50, 30)
        deselect_all_btn.clicked.connect(self.deselect_all_channels)
        right_buttons_layout.addWidget(select_all_btn)
        right_buttons_layout.addWidget(deselect_all_btn)

        button_main_layout.addLayout(chip_buttons_layout)
        button_main_layout.addStretch()
        button_main_layout.addLayout(right_buttons_layout)

        button_widget = QWidget()
        button_widget.setLayout(button_main_layout)

        # ========== 新增：手动 Y 轴范围控制 ==========
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

        # 将按钮区域和Y轴控制区域放在同一垂直布局中
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)
        top_layout.addWidget(self.pw)
        top_layout.addWidget(button_widget)
        top_layout.addWidget(ctrl_widget)

        # ========== 动态创建 64 个 CheckBox ==========
        self.checkboxes = []
        checkbox_widget = QWidget()
        checkbox_layout = QGridLayout(checkbox_widget)
        checkbox_layout.setSpacing(2)

        for i in range(self.curves_num):
            cb = QtWidgets.QCheckBox(f"Ch{i + 1}")
            cb.stateChanged.connect(self.cb_handler)
            self.checkboxes.append(cb)
            row = i // 8
            col = i % 8
            checkbox_layout.addWidget(cb, row, col)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidget(checkbox_widget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setMinimumHeight(150)
        # ============================================

        # ========== QSplitter 布局 ==========
        bottom_widget = self.scrollArea

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([400, 300])
        splitter.setHandleWidth(5)

        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)

        self.gridLayout.addWidget(splitter, 0, 0)
        # ====================================

        # ========== 数据缓冲区 ==========
        self.data_buffer = np.empty(shape=(0, 64))
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

        # 初始化期间断开信号，防止 cb_handler 提前保存
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
        self.resize(self.settings.value("size", QSize(800, 600)))
        if (self.settings.value("pos") is not None) and (self.settings.value("size") is not None):
            screenRect = QApplication.primaryScreen().geometry()
            if self.settings.value("pos").x() < (screenRect.width() - 100) and \
                    self.settings.value("pos").y() < (screenRect.height() - 100):
                self.move(self.settings.value("pos", QPoint(50, 50)))

    def deal_with_data_inlet(self, ts, arr):
        if arr.shape[1] == 1:
            arr = np.hstack((arr, np.zeros(shape=(arr.shape[0], 63))))
        self.data_buffer = np.concatenate((self.data_buffer, arr), axis=0)
        self.ts_buffer = np.concatenate((self.ts_buffer, ts), axis=0)
        # 按时间窗口裁剪
        t_cutoff = self.ts_buffer[-1] - self.max_buffer_secs
        keep = self.ts_buffer >= t_cutoff
        if not np.all(keep):
            idx = np.argmax(keep)  # 第一个 True 的位置
            self.data_buffer = self.data_buffer[idx:, :]
            self.ts_buffer = self.ts_buffer[idx:]

    def _update_psd(self):
        if self.data_buffer.shape[0] < 2 or self.ts_buffer.shape[0] < 2:
            return

        t_cutoff = self.ts_buffer[-1] - self.window_sec
        keep = self.ts_buffer >= t_cutoff
        if keep.sum() < 64:
            return  # welch nperseg 至少需要这么多点

        segment = self.data_buffer[keep, :]
        ts_seg = self.ts_buffer[keep]

        # 从时间戳推算真实采样率
        if len(ts_seg) > 1 and ts_seg[-1] > ts_seg[0]:
            actual_fs = float((len(ts_seg) - 1) / (ts_seg[-1] - ts_seg[0]))
        else:
            actual_fs = self.fs
        desired_nperseg = max(64, min(256, int(self.nperseg_sec * actual_fs)))
        # 根据实际数据长度裁剪 nperseg，避免 scipy 内部自动裁剪后 noverlap >= nperseg
        actual_nperseg = min(desired_nperseg, len(segment))
        if actual_nperseg < 16:
            return
        noverlap = actual_nperseg // 2

        for ch in range(self.curves_num):
            if ch < len(self.show_ch) and self.show_ch[ch]:
                f, psd = signal.welch(
                    segment[:, ch],
                    fs=actual_fs,
                    nperseg=actual_nperseg,
                    noverlap=noverlap,
                )
                psd_db = 10.0 * np.log10(np.maximum(psd, 1e-12))
                self.curves[ch].setData(x=f, y=psd_db + self.offset_db * ch)

        # 根据当前模式调整 Y 轴
        if self.fixed_y_checkbox.isChecked():
            self._apply_fixed_y_range()
        else:
            # 自动缩放模式：启用自动范围
            self.pw.enableAutoRange(axis='y')

    def _on_fixed_y_toggled(self, checked):
        self.y_min_spin.setEnabled(checked)
        self.y_max_spin.setEnabled(checked)
        if checked:
            # 禁用自动缩放，并应用固定范围
            self.pw.disableAutoRange(axis='y')
            self._apply_fixed_y_range()
        else:
            # 恢复自动缩放
            self.pw.enableAutoRange(axis='y')

    def _apply_fixed_y_range(self):
        """根据 spinbox 的值设置 Y 轴范围"""
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

    def select_chip(self, chip_index):
        start = chip_index * 8
        end = start + 8
        for i in range(start, end):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(True)

    def select_all_channels(self):
        for i in range(self.curves_num):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(True)

    def deselect_all_channels(self):
        for i in range(self.curves_num):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(False)

    def reset_view(self):
        # 重置视图时，如果处于手动模式，保持固定范围；否则恢复自动范围
        if self.fixed_y_checkbox.isChecked():
            self._apply_fixed_y_range()
        else:
            self.pw.autoRange(axis='x')
            self.pw.autoRange(axis='y')
        self.pw.repaint()

    def set_playback_mode(self, active):
        """回放期间暂停内部 PSD 定时器，避免重复计算导致卡顿"""
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