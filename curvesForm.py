from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QSplitter, QVBoxLayout
import numpy as np
import json
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QScrollArea, QGridLayout, QWidget, QVBoxLayout, QHBoxLayout, QPushButton

import pyqtgraph as pg
import os

qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "curvesform.ui")
ini_file = os.path.join(os.path.dirname(__file__), "ui_config", "curveFormSetting.ini")

Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)
import debugPrinter as dp

config_file = os.path.join(os.path.dirname(__file__), "ui_config", 'user_config_curve_form.json')


class CurvesForm(QtWidgets.QWidget, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowTitle("Signals")

        # ========== 创建波形显示区域 ==========
        self.pw = pg.plot(title="sig")
        self.plt = self.pw.getPlotItem()

        # ========== 禁用鼠标拖动横坐标 ==========
        vb = self.pw.getPlotItem().getViewBox()
        vb.setMouseEnabled(x=False, y=True)  # 禁用X轴拖动，保留Y轴
        # ====================================

        # ========== 配置：64个EEG通道 + 4个ACC通道 ==========
        self.curves_num_constant = 68
        curves_eeg_num = 64
        curves_acc_num = 4
        # =================================================

        # ========== 创建芯片按钮区域 ==========
        button_main_layout = QHBoxLayout()
        button_main_layout.setContentsMargins(0, 0, 0, 0)

        self.chip_buttons = []
        chip_buttons_layout = QHBoxLayout()
        chip_buttons_layout.setSpacing(5)

        for chip in range(8):
            btn = QPushButton(f"芯片{chip + 1}")
            btn.setToolTip(f"Ch{chip * 8 + 1}-{chip * 8 + 8}")
            btn.setFixedSize(60, 30)
            btn.clicked.connect(lambda checked, c=chip: self.select_chip(c))
            self.chip_buttons.append(btn)
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
        # =================================================

        # ========== 动态创建68个CheckBox ==========
        self.checkboxes = []
        checkbox_widget = QWidget()
        checkbox_layout = QGridLayout(checkbox_widget)
        checkbox_layout.setSpacing(2)

        for i in range(self.curves_num_constant):
            if i < 64:
                cb = QtWidgets.QCheckBox(f"Ch{i + 1}")
            else:
                acc_labels = ['x', 'y', 'z', 't']
                cb = QtWidgets.QCheckBox(acc_labels[i - 64])
            cb.stateChanged.connect(self.cb_handler)
            self.checkboxes.append(cb)
            row = i // 8
            col = i % 8
            checkbox_layout.addWidget(cb, row, col)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidget(checkbox_widget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setMinimumHeight(150)
        # =================================================

        self.scale_offset = 100

        # ========== 使用 QSplitter 实现可调整大小 ==========
        # 创建上半部分容器（波形 + 按钮）
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)
        top_layout.addWidget(self.pw)
        top_layout.addWidget(button_widget)

        # 创建下半部分容器（复选框区域）
        bottom_widget = self.scrollArea

        # 创建分割器，允许上下拖动调整大小
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([400, 300])  # 初始大小：波形区域400像素，复选框区域300像素
        splitter.setHandleWidth(5)  # 分割线宽度
        # =================================================

        # 确保 gridLayout 存在
        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)

        # 将分割器添加到主布局
        self.gridLayout.addWidget(splitter, 0, 0)

        self.pw.setLabel('bottom', 'Time', 's')

        self.curve_data_max_len = 1000
        self.curve_data_max_len_acc = 100

        self.curves = []
        self.curves_acc = []

        for i in range(self.curves_num_constant):
            pen = pg.mkPen(color='b', width=1, antialias=False)  # 关闭抗锯齿
            c = self.pw.plot()
            self.curves.append(c)

        self.data = np.empty(shape=(0, curves_eeg_num + 1))
        self.data_acc = np.empty(shape=(0, curves_acc_num + 1))

        self._dirty = False
        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._render)
        self._render_timer.start(10)  # 100fps

        # 加载配置文件
        if os.path.exists(config_file):
            with open(config_file, 'r') as file:
                self.usr_config_json = json.load(file)
        else:
            self.usr_config_json = {}

        self.show_ch = np.array(self.usr_config_json.get('CH', []))
        if len(self.show_ch) != self.curves_num_constant:
            self.show_ch = np.ones(self.curves_num_constant)
            self.usr_config_json['CH'] = list(self.show_ch)

        curves_num = len(self.curves) + len(self.curves_acc)

        # 初始化期间断开信号，防止 cb_handler 在设置复选框时提前保存
        for i in range(self.curves_num_constant):
            self.checkboxes[i].blockSignals(True)

        if self.show_ch.size == self.curves_num_constant:
            for i, ch in enumerate(self.show_ch):
                if i < curves_num:
                    if ch == 1:
                        self.checkboxes[i].setChecked(True)
                        self.curves[i].show()
                    else:
                        self.checkboxes[i].setChecked(False)
                        self.curves[i].hide()

        for i in range(self.curves_num_constant):
            self.checkboxes[i].blockSignals(False)

        self.settings = QSettings('./curveFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(270, 225)))
        if (self.settings.value("pos") is not None) and (self.settings.value("size") is not None):
            screenRect = QApplication.primaryScreen().geometry()
            self.height = screenRect.height()
            if self.settings.value("pos").x() < (screenRect.width() - 100) and \
                    self.settings.value("pos").y() < (screenRect.height() - 100):
                self.move(self.settings.value("pos", QPoint(50, 50)))

    def auto_range_y(self):
        """自动调整Y轴范围，使所有显示的通道都在视野内"""
        if len(self.data) > 0:
            # 获取所有显示通道的Y值
            all_y = []
            for i in range(min(self.data.shape[1] - 1, 64)):
                if i < len(self.show_ch) and self.show_ch[i]:
                    y_data = self.data[:, i + 1] * 0.3 + self.scale_offset * i
                    if len(y_data) > 0:
                        all_y.extend(y_data)

            if all_y:
                y_min = min(all_y)
                y_max = max(all_y)
                # 添加10%的边距
                margin = (y_max - y_min) * 0.1
                if margin == 0:
                    margin = 100
                self.pw.setYRange(y_min - margin, y_max + margin)

    def __del__(self):
        dp.dpt('del curvesform')

    def closeEvent(self, e):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        e.accept()

    def close_win(self):
        dp.dpt('curveform close')
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.close()

    def cb_handler(self):
        # 记录新增的通道（被勾选的通道）
        previous_shown = self.show_ch.copy() if hasattr(self, 'show_ch') else None

        for i in range(self.curves_num_constant):
            if self.checkboxes[i].isChecked():
                self.curves[i].show()
                self.show_ch[i] = 1
            else:
                self.show_ch[i] = 0
                self.curves[i].hide()

        self.usr_config_json['CH'] = list(self.show_ch)

        with open(config_file, "w") as outfile:
            json.dump(self.usr_config_json, outfile)

        # ========== 只有新增通道时才自动调整Y轴范围 ==========
        if previous_shown is not None:
            # 检查是否有新增的通道（之前未勾选，现在勾选了）
            new_channels = []
            for i in range(self.curves_num_constant):
                if i < len(previous_shown) and i < len(self.show_ch):
                    if previous_shown[i] == 0 and self.show_ch[i] == 1:
                        new_channels.append(i)

            # 如果有新增通道，才调整Y轴
            if len(new_channels) > 0:
                self.auto_range_y()
        # ====================================================

    def select_chip(self, chip_index):
        start = chip_index * 8
        end = start + 8
        for i in range(start, end):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(True)

    def select_all_channels(self):
        for i in range(64):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(True)

    def deselect_all_channels(self):
        for i in range(64):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(False)

    def reset_view(self):
        """重置视图，恢复波形显示"""
        if len(self.data) > 0:
            x_min = self.data[:, 0].min()
            x_max = self.data[:, 0].max()
            if x_min < x_max:
                self.pw.setXRange(x_min, x_max)
            self.pw.autoRange(axis='y')
            self.pw.repaint()

    def deal_with_data_inlet(self, elapsed_time, y):
        if y.shape[1] == 1:
            y = np.hstack((y, np.zeros(shape=(y.shape[0], 63))))

        t = np.expand_dims(elapsed_time, axis=1)
        d = np.hstack((t, y))

        self.data = np.concatenate((self.data, d), axis=0)

        num_del = self.data.shape[0] - self.curve_data_max_len
        if num_del > 0:
            self.data = np.delete(self.data, np.s_[:num_del], axis=0)

        self._dirty = True

    def _render(self):
        """QTimer 驱动：仅渲染可见通道的最近一段数据"""
        if not self._dirty or self.data.shape[0] < 2:
            return
        self._dirty = False
        x = self.data[:, 0]
        for i in range(min(self.data.shape[1] - 1, 64)):
            if i < len(self.show_ch) and self.show_ch[i]:
                voltage_value = self.data[:, i + 1] * 0.3
                self.curves[i].setData(x=x, y=voltage_value + self.scale_offset * i)

    def deal_with_data_acc_inlet(self, elapsed_time, y):
        t = np.expand_dims(elapsed_time, axis=1)
        d = np.hstack((t, y))

        self.data_acc = np.concatenate((self.data_acc, d), axis=0)

        num_del = self.data_acc.shape[0] - self.curve_data_max_len_acc
        if num_del > 0:
            self.data_acc = np.delete(self.data_acc, np.s_[:num_del], axis=0)

        curves_eeg_num = 64
        for i in range(self.data_acc.shape[1] - 1):
            index_for_acc_curves = i + curves_eeg_num
            if index_for_acc_curves < len(self.show_ch) and self.show_ch[index_for_acc_curves]:
                self.curves[index_for_acc_curves].setData(
                    x=self.data_acc[:, 0],
                    y=self.data_acc[:, i + 1]
                )