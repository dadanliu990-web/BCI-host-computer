# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QScrollArea, QGridLayout, QWidget, QLabel
from PyQt5.QtGui import QColor
import numpy as np
import os

import pyqtgraph as pg

qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "curvesform.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)


class ImpedanceForm(QtWidgets.QWidget, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowTitle("信号质量")

        # ========== 模式 ==========
        self._mode = 'signal_quality'  # 'signal_quality' or 'impedance'
        self._values = {}              # ch -> value
        self._data_buffer = np.empty(shape=(0, 64))
        self._sample_count = 0
        self._needs_update = False
        self._cached_std = None  # 缓存最新标准差，供 TopoMapForm 共享

        # ========== 状态标签 ==========
        self.status_label = QLabel("等待数据...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px; color: #888;")

        # ========== 图表 ==========
        self.pw = pg.plot(title="信号质量 / 阻抗")
        self.pw.setLabel('bottom', '通道')
        self.pw.setLabel('left', '值')
        self.pw.getPlotItem().getViewBox().setMouseEnabled(x=True, y=True)

        # 阈值线
        self._add_threshold_lines()

        # 柱状图
        self.bar_item = pg.BarGraphItem(x=np.arange(64), height=np.zeros(64), width=0.7)
        self.pw.addItem(self.bar_item)
        self.pw.getPlotItem().getViewBox().setXRange(-1, 64)

        # ========== 按钮 ==========
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_check_all = QPushButton("全部检测")
        self.btn_check_all.setFixedSize(100, 30)
        self.btn_check_all.clicked.connect(self._on_check_all)
        btn_layout.addWidget(self.btn_check_all)

        self.btn_recheck = QPushButton("重新检测")
        self.btn_recheck.setFixedSize(100, 30)
        self.btn_recheck.clicked.connect(self._on_recheck)
        btn_layout.addWidget(self.btn_recheck)

        btn_layout.addStretch()

        btn_widget = QWidget()
        btn_widget.setLayout(btn_layout)

        # ========== QSplitter 布局 ==========
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.pw)
        top_layout.addWidget(btn_widget)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_widget)
        splitter.setHandleWidth(3)

        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)
        self.gridLayout.addWidget(splitter, 0, 0)

        # ========== QSettings ==========
        self.settings = QSettings('./impedanceFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(500, 400)))
        pos = self.settings.value("pos")
        size = self.settings.value("size")
        if pos is not None and size is not None:
            screenRect = QApplication.primaryScreen().geometry()
            if pos.x() < screenRect.width() - 100 and pos.y() < screenRect.height() - 100:
                self.move(pos)

        # ========== 定时刷新 ==========
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._redraw)
        self._update_timer.start(1000)

    def _add_threshold_lines(self):
        """添加阈值参考线"""
        if self._mode == 'impedance':
            thresholds = [5, 10]  # kΩ
        else:
            thresholds = [100, 300]  # μV (stddev)
        colors = [(0, 200, 0, 100), (200, 200, 0, 100)]
        for thr, color in zip(thresholds, colors):
            line = pg.InfiniteLine(pos=thr, angle=0, pen=pg.mkPen(color, width=2, style=Qt.DashLine))
            self.pw.addItem(line)

    def deal_with_data_inlet(self, ts, arr):
        """接收实时 EEG 数据用于信号质量评估"""
        if arr.shape[1] == 1:
            arr = np.hstack((arr, np.zeros(shape=(arr.shape[0], 63))))
        self._data_buffer = np.concatenate((self._data_buffer, arr), axis=0)
        num_del = self._data_buffer.shape[0] - 1250  # 5秒
        if num_del > 0:
            self._data_buffer = np.delete(self._data_buffer, np.s_[:num_del], axis=0)
        self._needs_update = True

    def _compute_signal_quality(self):
        """软件端信号质量评估"""
        if self._data_buffer.shape[0] < 250:  # 至少1秒数据
            return None
        recent = self._data_buffer[-1250:, :]
        pp_values = np.ptp(recent, axis=0)
        std_values = np.std(recent, axis=0)
        abnormal = (pp_values > 500) | (std_values > 100)
        return {'pp': pp_values, 'std': std_values, 'abnormal': abnormal}

    def update_values(self, values):
        """更新阻抗值 (硬件模式) 或信号质量值 (软件模式)
        values: dict, key=channel(0-63), value=float
        """
        self._values = values
        self._needs_update = True

    def _on_check_all(self):
        """全部检测"""
        if self._mode == 'signal_quality':
            self._compute_and_display()
        self.status_label.setText("检测中...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px; color: #888;")

    def _on_recheck(self):
        """重新检测"""
        self._data_buffer = np.empty(shape=(0, 64))
        self._values = {}
        self.status_label.setText("等待数据...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px; color: #888;")
        self.bar_item.setOpts(height=np.zeros(64), brushes=[pg.mkBrush('#666')] * 64)

    def _compute_and_display(self):
        """执行信号质量计算并更新图表"""
        result = self._compute_signal_quality()
        if result is None:
            self.status_label.setText("数据不足，请等待至少1秒")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px; color: #E88;")
            return

        std_values = result['std']
        self._cached_std = std_values.copy()  # 缓存供 TopoMapForm 共享
        abnormal = result['abnormal']
        n_abnormal = np.sum(abnormal)

        # 更新状态文字
        if n_abnormal == 0:
            self.status_label.setText("全部正常")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px; color: #0A0;")
        else:
            self.status_label.setText(f"{n_abnormal} 个通道需调整")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px; color: #E33;")

        # 颜色分档
        colors = []
        for v in std_values:
            if v < 100:
                colors.append(pg.mkBrush(0, 180, 0))        # 绿色
            elif v < 300:
                colors.append(pg.mkBrush(220, 180, 0))       # 黄色
            else:
                colors.append(pg.mkBrush(220, 30, 30))       # 红色

        self.bar_item.setOpts(x=np.arange(64), height=std_values, width=0.7, brushes=colors)

    def _redraw(self):
        """定时更新"""
        if self._needs_update:
            self._compute_and_display()
            self._needs_update = False

    def get_signal_quality(self):
        """返回最新标准差数组 (64,) 供 TopoMapForm 共享；无数据时返回 None"""
        if self._cached_std is not None and self._cached_std.shape == (64,) and np.all(np.isfinite(self._cached_std)):
            return self._cached_std
        return None

    def set_playback_mode(self, active):
        """回放期间暂停内部信号质量定时器，避免重复计算导致卡顿"""
        if active:
            self._update_timer.stop()
        else:
            self._update_timer.start(1000)

    def closeEvent(self, e):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        # 通知主窗口取消阻抗按钮选中状态
        if hasattr(self, '_mw') and self._mw is not None:
            self._mw.btn_impedance.setChecked(False)
        e.accept()

    def close_win(self):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.close()
