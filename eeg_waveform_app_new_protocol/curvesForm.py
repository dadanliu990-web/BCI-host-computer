from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox
import numpy as np
import json
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget

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

        vb = self.pw.getPlotItem().getViewBox()
        vb.setMouseEnabled(x=False, y=True)

        # ========== 配置：4个EEG通道 ==========
        self.curves_num = 4
        self.ch_colors = [
            (50, 100, 220),   # Ch1: 蓝
            (50, 180, 50),    # Ch2: 绿
            (220, 50, 50),    # Ch3: 红
            (200, 150, 0),    # Ch4: 橙
        ]
        # =====================================

        # ========== Ch1-Ch4 CheckBox + 全选/清空 按钮 ==========
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        bottom_layout.setSpacing(6)

        self.checkboxes = []
        for i in range(self.curves_num):
            r, g, b = self.ch_colors[i]
            cb = QCheckBox(f"Ch{i + 1}")
            cb.setStyleSheet(f"color: rgb({r},{g},{b}); font-weight: bold;")
            cb.stateChanged.connect(self.cb_handler)
            self.checkboxes.append(cb)
            bottom_layout.addWidget(cb)

        bottom_layout.addStretch()

        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedSize(50, 28)
        select_all_btn.clicked.connect(self.select_all_channels)
        bottom_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("清空")
        deselect_all_btn.setFixedSize(50, 28)
        deselect_all_btn.clicked.connect(self.deselect_all_channels)
        bottom_layout.addWidget(deselect_all_btn)

        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_layout)
        # =====================================================

        # ========== 垂直布局：波形 + 底部控制栏 ==========
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)
        main_layout.addWidget(self.pw)
        main_layout.addWidget(bottom_widget)

        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)

        self.gridLayout.addWidget(main_widget, 0, 0)

        self.pw.setLabel('bottom', 'Time', 's')

        self.curve_data_max_len = 1000
        self.scale_offset = 100

        self.curves = []
        for i in range(self.curves_num):
            pen = pg.mkPen(color=self.ch_colors[i], width=1.2, antialias=False)
            c = self.pw.plot(pen=pen)
            self.curves.append(c)

        self.data = np.empty(shape=(0, self.curves_num + 1))

        self._dirty = False
        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._render)
        self._render_timer.start(10)

        # 加载配置文件
        if os.path.exists(config_file):
            with open(config_file, 'r') as file:
                self.usr_config_json = json.load(file)
        else:
            self.usr_config_json = {}

        self.show_ch = np.array(self.usr_config_json.get('CH', []))
        if len(self.show_ch) != self.curves_num:
            self.show_ch = np.ones(self.curves_num)
            self.usr_config_json['CH'] = list(self.show_ch)

        for i in range(self.curves_num):
            self.checkboxes[i].blockSignals(True)

        for i, ch in enumerate(self.show_ch):
            if i < self.curves_num:
                if ch == 1:
                    self.checkboxes[i].setChecked(True)
                    self.curves[i].show()
                else:
                    self.checkboxes[i].setChecked(False)
                    self.curves[i].hide()

        for i in range(self.curves_num):
            self.checkboxes[i].blockSignals(False)

        self.settings = QSettings('./curveFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(600, 400)))
        if (self.settings.value("pos") is not None) and (self.settings.value("size") is not None):
            screenRect = QApplication.primaryScreen().geometry()
            self.height = screenRect.height()
            if self.settings.value("pos").x() < (screenRect.width() - 100) and \
                    self.settings.value("pos").y() < (screenRect.height() - 100):
                self.move(self.settings.value("pos", QPoint(50, 50)))

    def auto_range_y(self):
        if len(self.data) > 0:
            all_y = []
            for i in range(min(self.data.shape[1] - 1, self.curves_num)):
                if i < len(self.show_ch) and self.show_ch[i]:
                    y_data = self.data[:, i + 1] * 0.3 + self.scale_offset * i
                    if len(y_data) > 0:
                        all_y.extend(y_data)

            if all_y:
                y_min = min(all_y)
                y_max = max(all_y)
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

        self.pw.enableAutoRange(axis='y')

    def select_all_channels(self):
        for i in range(self.curves_num):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(True)

    def deselect_all_channels(self):
        for i in range(self.curves_num):
            if i < len(self.checkboxes):
                self.checkboxes[i].setChecked(False)

    def reset_view(self):
        if len(self.data) > 0:
            x_min = self.data[:, 0].min()
            x_max = self.data[:, 0].max()
            if x_min < x_max:
                self.pw.setXRange(x_min, x_max)
            self.pw.autoRange(axis='y')
            self.pw.repaint()

    def deal_with_data_inlet(self, elapsed_time, y):
        if y.shape[1] == 1:
            y = np.hstack((y, np.zeros(shape=(y.shape[0], self.curves_num - 1))))

        t = np.expand_dims(elapsed_time, axis=1)
        d = np.hstack((t, y))

        self.data = np.concatenate((self.data, d), axis=0)

        num_del = self.data.shape[0] - self.curve_data_max_len
        if num_del > 0:
            self.data = np.delete(self.data, np.s_[:num_del], axis=0)

        self._dirty = True

    def _render(self):
        if not self._dirty or self.data.shape[0] < 2:
            return
        self._dirty = False
        x = self.data[:, 0]
        for i in range(min(self.data.shape[1] - 1, self.curves_num)):
            if i < len(self.show_ch) and self.show_ch[i]:
                voltage_value = self.data[:, i + 1] * 0.3
                self.curves[i].setData(x=x, y=voltage_value + self.scale_offset * i)
        self.pw.enableAutoRange(axis='y')

    def deal_with_data_acc_inlet(self, elapsed_time, y):
        pass
