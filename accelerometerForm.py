# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QLabel
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
import numpy as np
import pyqtgraph as pg
import os
from lsl_config import FS

qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "curvesform.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)


class AccelerometerForm(QtWidgets.QWidget, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowTitle("加速度计")

        self.max_buffer_len = 2500  # 10s at 250Hz

        # ========== 图表 ==========
        self.pw = pg.plot(title="加速度计")
        self.pw.setLabel('bottom', 'Time (s)')
        self.pw.setLabel('left', 'Acceleration (m/s²)')
        self.pw.addLegend()
        self.pw.getPlotItem().getViewBox().setMouseEnabled(x=True, y=True)

        self.curve_x = self.pw.plot(pen=pg.mkPen((220, 50, 50), width=1), name='ACC_X')
        self.curve_y = self.pw.plot(pen=pg.mkPen((50, 180, 50), width=1), name='ACC_Y')
        self.curve_z = self.pw.plot(pen=pg.mkPen((50, 100, 220), width=1), name='ACC_Z')
        self.curve_mag = self.pw.plot(pen=pg.mkPen((220, 220, 220), width=1.5), name='ACC_Mag')

        # ========== 数值标签 ==========
        self.value_label = QLabel("X: --  Y: --  Z: --  Mag: --")
        self.value_label.setStyleSheet("font-size: 12px; padding: 4px;")

        # ========== QSplitter 布局 ==========
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_layout.addWidget(self.pw)
        top_layout.addWidget(self.value_label)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top_widget)
        splitter.setHandleWidth(3)

        if not hasattr(self, 'gridLayout'):
            self.gridLayout = QtWidgets.QGridLayout(self)
            self.setLayout(self.gridLayout)
        self.gridLayout.addWidget(splitter, 0, 0)

        # ========== 数据缓冲区 ts + X + Y + Z + Mag ==========
        self.data_buffer = np.empty(shape=(0, 5))

        # ========== 更新定时器 ==========
        self._timer = QTimer()
        self._timer.timeout.connect(self._update)
        self._timer.start(200)

        # ========== QSettings ==========
        self.settings = QSettings('./accFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(500, 300)))
        pos = self.settings.value("pos")
        size = self.settings.value("size")
        if pos is not None and size is not None:
            screenRect = QApplication.primaryScreen().geometry()
            if pos.x() < screenRect.width() - 100 and pos.y() < screenRect.height() - 100:
                self.move(pos)

    def deal_with_data_inlet(self, ts, arr):
        """arr: (N,3) or (N,4) — X, Y, Z [, Mag]"""
        ts = np.asarray(ts).flatten()
        arr = np.atleast_2d(arr)
        n = arr.shape[0]
        mag = np.sqrt(arr[:, 0]**2 + arr[:, 1]**2 + arr[:, 2]**2)
        if arr.shape[1] >= 4:
            mag = arr[:, 3]
        dd = np.column_stack((ts, arr[:, :3], mag))
        self.data_buffer = np.concatenate((self.data_buffer, dd), axis=0)
        num_del = self.data_buffer.shape[0] - self.max_buffer_len
        if num_del > 0:
            self.data_buffer = np.delete(self.data_buffer, np.s_[:num_del], axis=0)

    def _update(self):
        if self.data_buffer.shape[0] < 2:
            return
        ts = self.data_buffer[:, 0]
        t_rel = ts - ts[0]
        self.curve_x.setData(x=t_rel, y=self.data_buffer[:, 1])
        self.curve_y.setData(x=t_rel, y=self.data_buffer[:, 2])
        self.curve_z.setData(x=t_rel, y=self.data_buffer[:, 3])
        self.curve_mag.setData(x=t_rel, y=self.data_buffer[:, 4])

        last = self.data_buffer[-1, :]
        self.value_label.setText(
            f"X: {last[1]:.3f}  Y: {last[2]:.3f}  Z: {last[3]:.3f}  Mag: {last[4]:.3f}  (m/s²)"
        )

    def reset_view(self):
        self.pw.autoRange(axis='x')
        self.pw.autoRange(axis='y')
        self.pw.repaint()

    def closeEvent(self, e):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        e.accept()

    def close_win(self):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.close()
