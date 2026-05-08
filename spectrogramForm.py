# -*- coding: utf-8 -*-

from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel, QSpinBox
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
import numpy as np
import pyqtgraph as pg
from scipy import signal
import os
from lsl_config import FS

qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "curvesform.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)


class SpectrogramForm(QtWidgets.QWidget, Ui_MainWindow):

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowTitle("时频谱图")

        self.fs = FS
        self.buffer_secs = 30
        self.nperseg_sec = 1.0       # STFT 每段时长（秒）
        self.update_interval_ms = 100   #10HZ刷新率

        self._channel = 0
        self._cmap = 'viridis'
        self._db_min = -20
        self._db_max = 90

        # 预构建 colormap 对象，避免 pyqtgraph 缺失 CSV 文件导致 FileNotFoundError
        self._cmaps = {}
        self._init_cmaps()

        # ========== ImageView ==========
        self.img = pg.ImageItem()
        self.pw = pg.PlotItem(title="Spectrogram")
        self.pw.setLabel('bottom', 'Time (s)')
        self.pw.setLabel('left', 'Frequency (Hz)')
        self.pw.addItem(self.img)
        self.pw.getViewBox().setMouseEnabled(x=True, y=True)

        # 纵向颜色条（置于时频谱图右侧）
        self.colorbar = pg.ColorBarItem(
            values=(self._db_min, self._db_max),
            colorMap=self._cmaps[self._cmap],
            label='Power (dB)',
            limits=(self._db_min, self._db_max),
        )
        self.colorbar.setImageItem(self.img)

        # ========== 控制面板 ==========
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        ctrl_layout.addWidget(QLabel("通道:"))
        self.ch_spin = QSpinBox()
        self.ch_spin.setRange(1, 64)
        self.ch_spin.setValue(1)
        self.ch_spin.valueChanged.connect(lambda v: setattr(self, '_channel', v - 1))
        ctrl_layout.addWidget(self.ch_spin)

        ctrl_layout.addWidget(QLabel("色图:"))
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(['viridis', 'inferno', 'jet', 'hot', 'plasma'])
        self.cmap_combo.currentTextChanged.connect(self._on_cmap_changed)
        ctrl_layout.addWidget(self.cmap_combo)

        ctrl_layout.addWidget(QLabel("dB Min:"))
        self.db_min_spin = QSpinBox()
        self.db_min_spin.setRange(-120, 120)
        self.db_min_spin.setValue(self._db_min)
        self.db_min_spin.valueChanged.connect(self._on_db_range_changed)
        ctrl_layout.addWidget(self.db_min_spin)

        ctrl_layout.addWidget(QLabel("dB Max:"))
        self.db_max_spin = QSpinBox()
        self.db_max_spin.setRange(-120, 120)
        self.db_max_spin.setValue(self._db_max)
        self.db_max_spin.valueChanged.connect(self._on_db_range_changed)
        ctrl_layout.addWidget(self.db_max_spin)

        ctrl_layout.addStretch()

        ctrl_widget = QWidget()
        ctrl_widget.setLayout(ctrl_layout)

        # ========== 图形视图 ==========
        self.graphics_view = pg.GraphicsLayoutWidget()
        self.graphics_view.addItem(self.pw, row=0, col=0)
        self.graphics_view.addItem(self.colorbar, row=0, col=1)

        # ========== QSplitter 布局 ==========
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_layout.addWidget(self.graphics_view)
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
        self.ts_buffer = np.empty(shape=(0,))

        # ========== 更新定时器 ==========
        self._timer = QTimer()
        self._timer.timeout.connect(self._update)
        self._timer.start(self.update_interval_ms)

        # ========== QSettings ==========
        self.settings = QSettings('./spectrogramFormSetting.ini', QSettings.IniFormat)
        self.resize(self.settings.value("size", QSize(600, 450)))
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
        self.ts_buffer = np.concatenate((self.ts_buffer, ts), axis=0)
        # 按时间窗口裁剪
        t_cutoff = self.ts_buffer[-1] - self.buffer_secs
        keep = self.ts_buffer >= t_cutoff
        if not np.all(keep):
            idx = np.argmax(keep)
            self.data_buffer = self.data_buffer[idx:, :]
            self.ts_buffer = self.ts_buffer[idx:]

    def _update(self):
        if self.data_buffer.shape[0] < 2 or self.ts_buffer.shape[0] < 2:
            return

        ch_data = self.data_buffer[:, self._channel]

        # 从时间戳推算真实采样率
        if len(self.ts_buffer) > 1 and self.ts_buffer[-1] > self.ts_buffer[0]:
            actual_fs = float((len(self.ts_buffer) - 1) / (self.ts_buffer[-1] - self.ts_buffer[0]))
        else:
            actual_fs = self.fs
        desired_nperseg = max(64, min(512, int(self.nperseg_sec * actual_fs)))
        # 根据实际数据长度裁剪，避免 scipy 内部裁剪后 noverlap >= nperseg
        actual_nperseg = min(desired_nperseg, len(ch_data))
        if actual_nperseg < 16:
            return
        noverlap = actual_nperseg * 3 // 4
        if noverlap >= actual_nperseg:
            noverlap = actual_nperseg // 2

        f, t, Sxx = signal.spectrogram(
            ch_data, fs=actual_fs, nperseg=actual_nperseg,
            noverlap=noverlap, mode='psd'
        )
        Sxx_db = 10.0 * np.log10(np.maximum(Sxx, 1e-12))
        Sxx_db = np.clip(Sxx_db, self._db_min, self._db_max)

        # 调整时间轴使最近的数据在右侧
        t_display = t - t[-1] if len(t) > 0 else t

        self.img.setImage(Sxx_db.T)
        self.img.setRect(pg.QtCore.QRectF(
            t_display[0], f[0],
            t_display[-1] - t_display[0], f[-1] - f[0]
        ))
        self.pw.setXRange(t_display[0], t_display[-1])
        self.pw.setYRange(0, 60)

    def _on_cmap_changed(self, cmap_name):
        self._cmap = cmap_name
        self.colorbar.setColorMap(self._cmaps[cmap_name])

    def _on_db_range_changed(self):
        self._db_min = self.db_min_spin.value()
        self._db_max = self.db_max_spin.value()
        self.colorbar.setLevels((self._db_min, self._db_max))

    def _init_cmaps(self):
        """预构建 colormap 对象 —— 优先内置，缺失则用硬编码颜色数组兜底"""
        specs = {
            'viridis': [(0.0, 68, 1, 84), (0.25, 58, 82, 139), (0.5, 32, 144, 140),
                        (0.75, 94, 201, 97), (1.0, 253, 231, 36)],
            'inferno': [(0.0, 0, 0, 4), (0.25, 65, 11, 84), (0.5, 180, 54, 72),
                        (0.75, 240, 126, 12), (1.0, 252, 255, 164)],
            'jet':     [(0.0, 0, 0, 127), (0.25, 0, 0, 255), (0.5, 0, 255, 255),
                        (0.75, 255, 255, 0), (1.0, 255, 0, 0)],
            'hot':     [(0.0, 0, 0, 0), (0.33, 255, 0, 0), (0.66, 255, 255, 0),
                        (1.0, 255, 255, 255)],
            'plasma':  [(0.0, 13, 8, 135), (0.25, 126, 3, 168), (0.5, 204, 71, 120),
                        (0.75, 248, 149, 64), (1.0, 240, 249, 33)],
        }
        for name, pts in specs.items():
            try:
                self._cmaps[name] = pg.colormap.get(name)
            except Exception:
                pos = np.array([p[0] for p in pts])
                colors = np.array([[p[1], p[2], p[3], 255] for p in pts], dtype=np.ubyte)
                self._cmaps[name] = pg.ColorMap(pos, colors)

    def reset_view(self):
        self.pw.autoRange(axis='x')
        self.pw.autoRange(axis='y')
        self.graphics_view.repaint()

    def closeEvent(self, e):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        e.accept()

    def close_win(self):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        self.close()
