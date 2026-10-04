# -*- coding: utf-8 -*-
"""
BCI 上位机 — LSL stream viewer.

Layout:
  ┌─────────────────────┬──────────────────────┐
  │  Time Series        │  FFT Plot            │
  │  Ch[1][2]...[8]     │  Ch[1][2]...[8]      │
  │  ┌── Ch1 ────────┐  │  ┌────────────────┐  │
  │  ├── Ch2 ────────┤  │  │   Spectrum     │  │
  │  │   ...          │  │  │                │  │
  │  └── Ch8 ────────┘  │  └────────────────┘  │
  │                      ├──────────────────────┤
  │                      │  控制面板             │
  │                      │  ·设备 ·滤波 ·LSL流   │
  └─────────────────────┴──────────────────────┘
"""
import os
import threading
from collections import deque
import numpy as np
import pyqtgraph as pg
import pylsl

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QCheckBox, QDoubleSpinBox, QComboBox,
    QTextBrowser, QMessageBox, QSplitter
)
from PyQt5.QtGui import QColor
from scipy.signal import welch

from stream_receiver import StreamReceiver, _resolve_by_name
from filter_controller import FilterController
from labrecorder_controller import LabRecorderController, RCS_PORT

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LABRECORDER_EXE = os.path.join(
    _SCRIPT_DIR, 'LabRecorder', 'LabRecorder-1.17.0-Win_amd64', 'LabRecorder.exe'
)
_CHECK_SVG = '"' + _SCRIPT_DIR.replace('\\', '/') + '/check.svg"'
PRESET_SOURCES = ['selfboard_eeg', 'openbci_eeg', 'obci_eeg', 'mi_eeg']
N_CHANNELS = 8

# Channel colors
CH_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
]


STYLE = """
QMainWindow {
    background-color: #ffffff;
}
QWidget {
    background-color: #ffffff;
    color: #333;
    font-size: 17px;
}
QLabel {
    color: #333;
    font-size: 17px;
    background: transparent;
}
QGroupBox {
    color: #333;
    font-weight: bold;
    font-size: 17px;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 14px;
    padding: 14px 8px 8px 8px;
    background-color: #fafafa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #555;
    font-size: 17px;
    background-color: #fafafa;
}
QComboBox {
    background-color: white;
    color: #333;
    border: 1px solid #bbb;
    border-radius: 3px;
    padding: 4px 10px;
    font-size: 17px;
    min-height: 30px;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: white;
    color: #333;
    font-size: 17px;
    selection-background-color: #4a9eff;
    selection-color: white;
}
QDoubleSpinBox {
    background-color: white;
    color: #333;
    border: 1px solid #bbb;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 17px;
    min-height: 30px;
}
QCheckBox {
    color: #333;
    font-size: 17px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    background: white;
    border: 1px solid #999;
    border-radius: 2px;
}
QCheckBox::indicator:hover {
    border: 1px solid #4a9eff;
}
QCheckBox::indicator:checked {
    background: #4a9eff;
    border: 1px solid #4a9eff;
    image: url(__CHECK_SVG_PATH__);
}
QListWidget {
    background-color: white;
    color: #333;
    border: 1px solid #bbb;
    border-radius: 3px;
    font-size: 15px;
    outline: none;
}
QListWidget::item { padding: 4px 6px; }
QListWidget::item:hover { background-color: #e8f0fe; }
QListWidget::item:selected { background-color: #4a9eff; color: white; }
QTextBrowser {
    background-color: white;
    color: #555;
    border: 1px solid #ddd;
    border-radius: 3px;
    font-size: 14px;
    padding: 4px;
}
QSplitter::handle { background-color: #ddd; width: 3px; }
QStatusBar {
    background-color: #f5f5f5;
    color: #666;
    border-top: 1px solid #ddd;
    font-size: 14px;
}
"""
STYLE = STYLE.replace('__CHECK_SVG_PATH__', _CHECK_SVG)


def _make_ch_button(idx, color):
    """Create a single colored checkable channel button."""
    b = QPushButton(f'{idx+1}')
    b.setCheckable(True)
    b.setChecked(True)
    b.setFixedSize(38, 30)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: #f0f0f0;
            color: {color};
            border: 2px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{ border: 2px solid {color}; background-color: #fff; }}
        QPushButton:checked {{
            background-color: {color};
            color: white;
            border: 2px solid {color};
        }}
    """)
    return b


class _RingBuffer:
    """Fixed-size ring buffer: O(1) append, O(n) read (once per render)."""
    __slots__ = ('_buf', '_head', '_count', '_maxlen')

    def __init__(self, maxlen, n_cols):
        self._maxlen = maxlen
        self._buf = np.zeros((maxlen, n_cols))
        self._head = 0
        self._count = 0

    def append(self, data):
        n = len(data)
        if n == 0:
            return
        if n >= self._maxlen:
            self._buf[:] = data[-self._maxlen:]
            self._head = 0
            self._count = self._maxlen
            return
        end = self._head + n
        if end <= self._maxlen:
            self._buf[self._head:end] = data
        else:
            first = self._maxlen - self._head
            self._buf[self._head:] = data[:first]
            self._buf[:end - self._maxlen] = data[first:]
        self._head = end % self._maxlen
        self._count = min(self._count + n, self._maxlen)

    def read(self):
        """Return a copy of all data in chronological order."""
        if self._count == 0:
            return np.empty((0, self._buf.shape[1]))
        if self._count < self._maxlen:
            return self._buf[:self._count].copy()
        return np.concatenate([self._buf[self._head:], self._buf[:self._head]])

    def clear(self):
        self._head = 0
        self._count = 0


class MainWindow(QMainWindow):
    evt_win = pyqtSignal(str, str)
    _scan_done = pyqtSignal(list)
    _resolve_done = pyqtSignal(str, object)
    _lr_launched = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('BCI 上位机')
        # Cross-thread callbacks — pyqtSignal is thread-safe
        self._scan_done.connect(self._apply_scan_results)
        self._resolve_done.connect(self._finish_connect)
        self._lr_launched.connect(self._on_lr_launched)
        self.setMinimumSize(1200, 780)
        self.setStyleSheet(STYLE)

        self._active_signal_name = None
        self._active_signal_srate = 250
        self._connected = False
        self._actual_ch = N_CHANNELS
        self._marker = ''

        self.receiver = StreamReceiver()
        self.filter_ctrl = FilterController(n_channels=N_CHANNELS, fs=250)
        self.lrc = LabRecorderController(LABRECORDER_EXE, rcs_port=RCS_PORT)

        self._wave_maxlen = 1250
        self._wave_buf = _RingBuffer(self._wave_maxlen, N_CHANNELS + 1)
        self._spec_buf = _RingBuffer(self._wave_maxlen * 2, N_CHANNELS + 1)
        self._dirty_wave = False
        self._ch_detected = False   # auto-detect channel count from first packet
        self._y_tick = 0              # counter: Y-axis updated every 500 ms
        self._pkt_count = 0           # packets received (reset each status tick)
        self._pkt_rate = 0            # packets / second
        self._auto_fs = 0             # auto-estimated sample rate from timestamps

        # LSL latency tracking
        self._latency_ms = 0.0
        self._latency_mean_ms = 0.0
        self._latency_max_ms = 0.0
        self._latency_history = deque(maxlen=500)

        # Threaded PSD state
        self._psd_lock = threading.Lock()
        self._psd_result = None
        self._psd_busy = False

        self._init_ui()
        self._connect_signals()
        self.receiver.start()

        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._render_wave)
        self._render_timer.start(50)

        self._psd_timer = QTimer()
        self._psd_timer.timeout.connect(self._on_psd_tick)
        self._psd_timer.start(100)

        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(1000)

        QTimer.singleShot(1000, self._auto_launch_lr)
        QTimer.singleShot(1500, self._refresh_streams)
        self._update_button_states()

    # ==================================================================
    # UI
    # ==================================================================
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ---- Main splitter: left (waveforms) | right (fft + controls) ----
        main_split = QSplitter(Qt.Horizontal)
        main_split.setHandleWidth(3)

        main_split.addWidget(self._build_waveform_panel())
        main_split.addWidget(self._build_right_panel())
        main_split.setSizes([600, 600])

        root.addWidget(main_split, 1)

        # ---- Status bar ----
        self._status_bar = QWidget()
        self._status_bar.setFixedHeight(32)
        self._status_bar.setStyleSheet('background-color: #f5f5f5; border-top: 1px solid #ddd;')
        sl = QHBoxLayout(self._status_bar)
        sl.setContentsMargins(8, 0, 8, 0)
        sl.setSpacing(20)

        self._st_fs = QLabel('Fs标称: — Hz')
        self._st_ch = QLabel('Ch: —')
        self._st_sample_rate = QLabel('接收样本率: — samples/s')
        self._st_chunk_rate = QLabel('Chunk率: — chunks/s')
        self._st_est_fs = QLabel('Fs估计: — Hz')
        self._st_latency = QLabel('LSL延迟: — ms')
        self._st_latency_mean = QLabel('均值: — ms')
        self._st_latency_max = QLabel('最大: — ms')
        self._st_marker = QLabel('Marker: —')
        self._st_lr = QLabel('LR: —')
        for lbl in [self._st_fs, self._st_ch, self._st_sample_rate, self._st_chunk_rate,
                     self._st_est_fs, self._st_latency, self._st_latency_mean,
                     self._st_latency_max, self._st_marker, self._st_lr]:
            lbl.setStyleSheet('color: #555; font-size: 14px; font-weight: bold; background: transparent;')
            sl.addWidget(lbl)
        sl.addStretch()

        root.addWidget(self._status_bar)

        self.statusBar().hide()
        self.resize(1300, 860)

    # ==================================================================
    # Left: Time Series — individual subplot per channel, 5s rolling window
    # ==================================================================
    WINDOW_SECS = 5.0

    def _build_waveform_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        title = QLabel('Time Series')
        title.setStyleSheet('font-weight: bold; font-size: 20px; color: #333;')
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(QLabel('Ch:'))

        btn_container = QWidget()
        btn_container.setStyleSheet('background: transparent;')
        self._ts_btn_layout = QHBoxLayout(btn_container)
        self._ts_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._ts_btn_layout.setSpacing(3)
        self._ts_btns = []
        for i in range(N_CHANNELS):
            b = _make_ch_button(i, CH_COLORS[i])
            b.toggled.connect(lambda checked, ch=i: self._on_ch_toggle(ch, checked))
            self._ts_btns.append(b)
            self._ts_btn_layout.addWidget(b)
        self._ts_btn_layout.addStretch()
        hdr.addWidget(btn_container)
        layout.addLayout(hdr)

        # GraphicsLayoutWidget — one row per channel
        self._ts_grid = pg.GraphicsLayoutWidget()
        self._ts_grid.setBackground('w')
        self._ts_plots = []
        self._ts_curves = []

        for i in range(N_CHANNELS):
            p = self._ts_grid.addPlot(row=i, col=0)
            p.setMouseEnabled(x=False, y=False)
            p.setMenuEnabled(False)
            p.hideButtons()  # hide the auto-range "A" button
            p.getViewBox().setDefaultPadding(0.0)
            p.getViewBox().setBackgroundColor('w')

            # Y-axis: right side — manually set to y_min..y_max every 500 ms
            p.showAxis('right')
            p.hideAxis('left')
            yax = p.getAxis('right')
            yax.setPen(CH_COLORS[i])
            yax.setTextPen(CH_COLORS[i])
            yax.setWidth(40)
            yax.setStyle(tickLength=-5)

            # X-axis: show on every subplot, with zero-line at Y=0
            xax = p.getAxis('bottom')
            xax.setPen('#999')
            xax.setTextPen('#555')
            xax.setStyle(tickLength=4)
            if i == N_CHANNELS - 1:
                xax.setLabel('Time', units='s', color='#555')
            else:
                xax.setLabel('')
            pen = pg.mkPen(color=CH_COLORS[i], width=1.2)
            curve = p.plot(pen=pen)
            self._ts_plots.append(p)
            self._ts_curves.append(curve)

        layout.addWidget(self._ts_grid, 1)
        return panel

    # ==================================================================
    # Right panel: FFT (top) + Controls (bottom)
    # ==================================================================
    def _build_right_panel(self):
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(3)

        splitter.addWidget(self._build_fft_section())
        splitter.addWidget(self._build_control_section())
        splitter.setSizes([400, 360])

        return splitter

    def _build_fft_section(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        title = QLabel('FFT Plot')
        title.setStyleSheet('font-weight: bold; font-size: 20px; color: #333;')
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(QLabel('Ch:'))

        btn_container = QWidget()
        btn_container.setStyleSheet('background: transparent;')
        self._fft_btn_layout = QHBoxLayout(btn_container)
        self._fft_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._fft_btn_layout.setSpacing(3)
        self._fft_btns = []
        for i in range(N_CHANNELS):
            b = _make_ch_button(i, CH_COLORS[i])
            self._fft_btns.append(b)
            self._fft_btn_layout.addWidget(b)
        self._fft_btn_layout.addStretch()
        hdr.addWidget(btn_container)
        layout.addLayout(hdr)

        # Frequency-style spectrum plot (single curve area, no spectrogram).
        self._fft_plot = pg.PlotWidget()
        self._fft_plot.setBackground('w')
        self._fft_plot.showGrid(x=True, y=True, alpha=0.3)
        self._fft_plot.setLabel('left', 'Amplitude', units='uV',
                                **{'color': '#000', 'font-size': '12pt'})
        self._fft_plot.setLabel('bottom', 'Frequency', units='Hz',
                                **{'color': '#000', 'font-size': '12pt'})
        self._fft_plot.setMouseEnabled(x=False, y=True)
        self._fft_plot.setXRange(0, 60, padding=0)
        self._fft_plot.addLegend(labelTextSize='12pt')

        self._fft_curves = []
        for i in range(N_CHANNELS):
            pen = pg.mkPen(color=CH_COLORS[i], width=1.8)
            self._fft_curves.append(
                self._fft_plot.plot(pen=pen, name=f'Ch{i + 1}')
            )
        layout.addWidget(self._fft_plot, 1)
        return panel

    def _build_control_section(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- Stream list (scan results) ----
        self.stream_list = QListWidget()
        self.stream_list.setMaximumHeight(90)
        self.stream_list.itemDoubleClicked.connect(self._on_dblclick)
        layout.addWidget(self.stream_list)

        # ---- Device row ----
        dev_row = QHBoxLayout()
        dev_row.setSpacing(6)
        dev_row.addWidget(QLabel('LSL 流:'))
        self.source_combo = QComboBox()
        self.source_combo.setEditable(True)
        self.source_combo.lineEdit().setPlaceholderText('输入流名称...')
        dev_row.addWidget(self.source_combo, 1)
        layout.addLayout(dev_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_connect = self._make_btn('连接', '#2ecc71', '#27ae60')
        self.btn_connect.clicked.connect(self._connect_stream)
        self.btn_connect.setEnabled(False)
        btn_row.addWidget(self.btn_connect)

        self.btn_disconnect = self._make_btn('断开', '#e74c3c', '#c0392b')
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_disconnect.setEnabled(False)
        btn_row.addWidget(self.btn_disconnect)

        self.btn_scan = self._make_btn('扫描流', '#3498db', '#2980b9')
        self.btn_scan.clicked.connect(self._refresh_streams)
        btn_row.addWidget(self.btn_scan)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ---- Separator ----
        layout.addWidget(self._separator())

        # ---- Filter row ----
        filt_row1 = QHBoxLayout()
        filt_row1.setSpacing(4)
        self.hp_check = QCheckBox('HP')
        self.hp_check.setChecked(False)
        self.hp_check.toggled.connect(self._on_hp_check)
        filt_row1.addWidget(self.hp_check)
        self.hp_spin = QDoubleSpinBox()
        self.hp_spin.setRange(0.1, 30.0)
        self.hp_spin.setSingleStep(0.1)
        self.hp_spin.setDecimals(1)
        self.hp_spin.setValue(0.5)
        self.hp_spin.setSuffix(' Hz')
        self.hp_spin.setEnabled(False)
        self.hp_spin.valueChanged.connect(self._apply_filters)
        filt_row1.addWidget(self.hp_spin)

        filt_row1.addSpacing(12)

        self.lp_check = QCheckBox('LP')
        self.lp_check.setChecked(False)
        self.lp_check.toggled.connect(self._on_lp_check)
        filt_row1.addWidget(self.lp_check)
        self.lp_spin = QDoubleSpinBox()
        self.lp_spin.setRange(5.0, 120.0)
        self.lp_spin.setSingleStep(1.0)
        self.lp_spin.setDecimals(0)
        self.lp_spin.setValue(40.0)
        self.lp_spin.setSuffix(' Hz')
        self.lp_spin.setEnabled(False)
        self.lp_spin.valueChanged.connect(self._apply_filters)
        filt_row1.addWidget(self.lp_spin)
        filt_row1.addStretch()
        layout.addLayout(filt_row1)

        filt_row2 = QHBoxLayout()
        filt_row2.setSpacing(4)
        filt_row2.addWidget(QLabel('陷波:'))
        self.notch_combo = QComboBox()
        self.notch_combo.addItems(['Off', '50 Hz', '60 Hz'])
        self.notch_combo.setCurrentIndex(1)
        self.notch_combo.currentIndexChanged.connect(self._on_notch_changed)
        filt_row2.addWidget(self.notch_combo)

        filt_row2.addSpacing(12)
        filt_row2.addWidget(QLabel('带宽:'))
        self.notch_bw = QDoubleSpinBox()
        self.notch_bw.setRange(0.5, 10.0)
        self.notch_bw.setSingleStep(0.5)
        self.notch_bw.setDecimals(1)
        self.notch_bw.setValue(1.0)
        self.notch_bw.setSuffix(' Hz')
        self.notch_bw.valueChanged.connect(self._apply_filters)
        filt_row2.addWidget(self.notch_bw)
        filt_row2.addStretch()
        layout.addLayout(filt_row2)

        # ---- Separator ----
        layout.addWidget(self._separator())

        # LR status & launch button
        lr_row = QHBoxLayout()
        lr_row.setSpacing(8)
        self.lr_lbl = QLabel('LabRecorder: —')
        self.lr_lbl.setStyleSheet('color: #888; font-size: 15px; padding: 2px;')
        lr_row.addWidget(self.lr_lbl)
        lr_row.addStretch()
        self.btn_launch_lr = self._make_btn('启动 LR', '#f39c12', '#e67e22')
        self.btn_launch_lr.clicked.connect(self._manual_launch_lr)
        lr_row.addWidget(self.btn_launch_lr)
        layout.addLayout(lr_row)

        # Log
        self.log_info = QTextBrowser()
        self.log_info.setReadOnly(True)
        self.log_info.document().setMaximumBlockCount(200)
        self.log_info.setMaximumHeight(55)
        layout.addWidget(self.log_info)

        layout.addStretch()

        self._populate_combo()
        return panel

    @staticmethod
    def _make_btn(text, color, hover_color, checkable=False):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(30)
        b.setCheckable(checkable)
        b.setStyleSheet(f"""
            QPushButton {{
                background-color: {color}; color: white;
                border: none; border-radius: 4px;
                padding: 6px 18px; font-weight: bold; font-size: 16px;
            }}
            QPushButton:hover {{ background-color: {hover_color}; }}
            QPushButton:checked {{ background-color: #95a5a6; color: white; }}
            QPushButton:disabled {{ background-color: #bdc3c7; color: #ecf0f1; }}
        """)
        return b

    @staticmethod
    def _separator():
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet('background-color: #ddd;')
        return line

    def _update_channel_display(self, actual_ch):
        """Called once when the first data packet reveals the true channel count.
        Hides buttons, plots and curves for channels beyond the actual count."""
        self._actual_ch = actual_ch
        for i in range(N_CHANNELS):
            visible = i < actual_ch
            self._ts_btns[i].setVisible(visible)
            self._fft_btns[i].setVisible(visible)
            self._fft_curves[i].setVisible(visible)
            if hasattr(self, '_ts_plots') and i < len(self._ts_plots):
                self._ts_plots[i].setVisible(visible)

    def _update_status(self):
        """Refresh the bottom status bar (1 Hz)."""
        self._st_fs.setText(f'Fs标称: {self._active_signal_srate:.0f} Hz')
        self._st_ch.setText(f'Ch: {self._actual_ch}')

        # Chunk rate — packets per second
        self._pkt_rate = self._pkt_count
        self._pkt_count = 0
        self._st_chunk_rate.setText(f'Chunk率: {self._pkt_rate} chunks/s')

        # Sample rate & Fs estimate from ring-buffer timestamps (1–5 s window)
        data = self._wave_buf.read()
        if data.shape[0] >= 10:
            ts = data[:, 0]
            span = ts[-1] - ts[0]
            if span > 0.5:
                samples_per_sec = (len(ts) - 1) / span
                self._st_sample_rate.setText(f'接收样本率: {samples_per_sec:.1f} samples/s')
                # Fs estimate via median inter-sample interval (robust)
                dt = np.diff(ts[-min(len(ts), 500):])  # last ~500 samples
                if len(dt) > 10:
                    median_dt = float(np.median(dt))
                    if median_dt > 0:
                        self._st_est_fs.setText(f'Fs估计: {1.0 / median_dt:.1f} Hz')
                        self._auto_fs = 1.0 / median_dt  # for downstream use
            else:
                self._st_sample_rate.setText('接收样本率: — samples/s')
                self._st_est_fs.setText('Fs估计: — Hz')
        else:
            self._st_sample_rate.setText('接收样本率: — samples/s')
            self._st_est_fs.setText('Fs估计: — Hz')

        # LSL latency
        if self._latency_history:
            self._st_latency.setText(f'LSL延迟: {self._latency_ms:.1f} ms')
            self._st_latency_mean.setText(f'均值: {self._latency_mean_ms:.1f} ms')
            self._st_latency_max.setText(f'最大: {self._latency_max_ms:.1f} ms')
        else:
            self._st_latency.setText('LSL延迟: — ms')
            self._st_latency_mean.setText('均值: — ms')
            self._st_latency_max.setText('最大: — ms')

        self._st_marker.setText(f'Marker: {self._marker or "—"}')
        lr_text = 'Running' if self.lrc.running else '—'
        lr_color = '#27ae60' if self.lrc.running else '#888'
        self._st_lr.setText(f'LR: {lr_text}')
        self._st_lr.setStyleSheet(f'color: {lr_color}; font-size: 14px; font-weight: bold; background: transparent;')

    def _populate_combo(self):
        self.source_combo.clear()
        for name in PRESET_SOURCES:
            self.source_combo.addItem(name)
        if hasattr(self, 'stream_list'):
            for i in range(self.stream_list.count()):
                n = self.stream_list.item(i).data(Qt.UserRole)
                if n and n not in [self.source_combo.itemText(j) for j in range(self.source_combo.count())]:
                    self.source_combo.addItem(n)

    # ==================================================================
    # LabRecorder
    # ==================================================================
    def _auto_launch_lr(self):
        if os.path.exists(LABRECORDER_EXE):
            threading.Thread(target=self._lr_launch_worker, daemon=True).start()

    def _manual_launch_lr(self):
        if not os.path.exists(LABRECORDER_EXE):
            self.lr_lbl.setText('LabRecorder: 未找到 LabRecorder.exe')
            self.lr_lbl.setStyleSheet('color: #e74c3c; font-weight: bold; font-size: 15px;')
            return
        if self.lrc.running:
            self.lr_lbl.setText('LabRecorder: 已在运行')
            self.lr_lbl.setStyleSheet('color: #27ae60; font-weight: bold; font-size: 15px;')
            return
        self.btn_launch_lr.setEnabled(False)
        self.btn_launch_lr.setText('启动中...')
        QApplication.processEvents()
        threading.Thread(target=self._lr_launch_worker, daemon=True).start()

    def _lr_launch_worker(self):
        """Background: launch LabRecorder (subprocess + RCS wait up to 15 s)."""
        ok = self.lrc.launch(study_name='eeg_session', save_path='./recordings')
        self._lr_launched.emit(ok)

    def _on_lr_launched(self, ok):
        """Main thread: update UI after background LR launch."""
        if ok:
            self.lr_lbl.setText('LabRecorder: 已启动')
            self.lr_lbl.setStyleSheet('color: #27ae60; font-weight: bold; font-size: 15px;')
            self._st_lr.setText('LR: Running')
            self._st_lr.setStyleSheet('color: #27ae60; font-size: 14px; font-weight: bold; background: transparent;')
            self.btn_launch_lr.setText('重启 LR')
            self.btn_launch_lr.setStyleSheet(
                'background-color: #27ae60; color: white; border: none; border-radius: 4px;'
                'padding: 6px 18px; font-weight: bold; font-size: 16px;'
            )
        else:
            self.lr_lbl.setText('LabRecorder: 启动失败')
            self.lr_lbl.setStyleSheet('color: #e74c3c; font-weight: bold; font-size: 15px;')
            self.btn_launch_lr.setText('重试启动')
        self.btn_launch_lr.setEnabled(True)

    # ==================================================================
    # Stream
    # ==================================================================
    def _connect_signals(self):
        self.receiver.evt_data.connect(self._on_data)

    def _connect_stream(self):
        name = self.source_combo.currentText().strip()
        if not name:
            return
        if self._active_signal_name:
            self._disconnect_internal()

        self.btn_connect.setEnabled(False)
        self.btn_connect.setText('连接中...')
        QApplication.processEvents()
        threading.Thread(target=self._connect_worker, args=(name,), daemon=True).start()

    def _connect_worker(self, name):
        """Background: resolve stream by name (blocking LSL call)."""
        info = _resolve_by_name(name, timeout=2.0)
        self._resolve_done.emit(name, info)

    def _finish_connect(self, name, info):
        """Main thread: complete connection after async name resolution.
        Uses subscribe_info() to avoid a second blocking resolve call."""
        if info is None:
            self.log_info.append(f'> 未找到 "{name}"')
            self._update_button_states()
            return

        stype = info.type().lower()
        if stype == 'markers':
            self.receiver.subscribe_info(name, info, 'Marker')
            self.log_info.append(f'> 已订阅 Marker: {name}')
            self._update_button_states()
            return

        ok = self.receiver.subscribe_info(name, info, 'Signal')
        if not ok:
            self.log_info.append(f'> 无法订阅 "{name}"')
            self._update_button_states()
            return

        self._active_signal_name = name
        self._active_signal_srate = info.nominal_srate() or 250
        self._connected = True
        self._actual_ch = N_CHANNELS
        self._ch_detected = False   # will be auto-detected from first packet

        self.filter_ctrl.set_fs(self._active_signal_srate)
        self.filter_ctrl.set_n_channels(N_CHANNELS)
        self._wave_maxlen = int(5.0 * self._active_signal_srate)
        self._wave_buf = _RingBuffer(self._wave_maxlen, N_CHANNELS + 1)
        self._spec_buf = _RingBuffer(self._wave_maxlen * 2, N_CHANNELS + 1)

        self.log_info.append(f'> 已连接: {name} ({self._actual_ch}ch, {self._active_signal_srate:.0f}Hz)')
        self._update_status()
        self._update_button_states()

        if self.lrc.running:
            self.lrc.select_all()

    def _disconnect_internal(self):
        if self._active_signal_name:
            self.receiver.unsubscribe(self._active_signal_name)
        self._active_signal_name = None
        self._connected = False
        self._actual_ch = N_CHANNELS
        self._st_fs.setText('Fs标称: — Hz')
        self._st_ch.setText('Ch: —')
        self._st_chunk_rate.setText('Chunk率: — chunks/s')
        self._st_sample_rate.setText('接收样本率: — samples/s')
        self._st_est_fs.setText('Fs估计: — Hz')
        self._st_latency.setText('LSL延迟: — ms')
        self._st_latency_mean.setText('均值: — ms')
        self._st_latency_max.setText('最大: — ms')
        self._latency_history.clear()
        self._update_button_states()

    def _on_disconnect_clicked(self):
        if self._active_signal_name is None:
            return
        self._disconnect_internal()
        self.log_info.append('> 已断开连接')

    def _update_button_states(self):
        """Enable/disable connect & disconnect buttons + restore label text."""
        if self._connected:
            self.btn_connect.setEnabled(False)
            self.btn_connect.setText('连接')
            self.btn_disconnect.setEnabled(True)
        else:
            self.btn_connect.setEnabled(True)
            self.btn_connect.setText('连接')
            self.btn_disconnect.setEnabled(False)

    def _on_dblclick(self, item):
        name = item.data(Qt.UserRole)
        if name:
            self.source_combo.setCurrentText(name)
            self._connect_stream()

    # ==================================================================
    # Scan
    # ==================================================================
    def _refresh_streams(self):
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText('扫描中...')
        QApplication.processEvents()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        """Background: scan LSL streams (blocking call)."""
        streams = self.receiver.scan_streams()
        self._scan_done.emit(streams)

    def _apply_scan_results(self, streams):
        """Main thread: populate stream list from background scan."""
        self.stream_list.clear()
        for info in streams:
            lbl = f'[{info.type()}] {info.name()}  ({info.channel_count()}ch, {info.nominal_srate():.0f}Hz)'
            item = QListWidgetItem(lbl)
            item.setData(Qt.UserRole, info.name())
            item.setToolTip('Double-click to connect')
            if info.type().lower() in ('eeg', 'signal', 'exg'):
                item.setForeground(QColor('#2ca02c'))
            elif info.type().lower() == 'markers':
                item.setForeground(QColor('#ff7f0e'))
            self.stream_list.addItem(item)
        self._populate_combo()
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText('扫描流')
        self.log_info.append(f'> 扫描完成: 发现 {len(streams)} 个流')

    # ==================================================================
    # Data
    # ==================================================================
    def _on_data(self, stream_name, ts, samples):
        if stream_name != self._active_signal_name:
            return
        # Auto-detect channel count from first data packet
        if not self._ch_detected:
            self._ch_detected = True
            actual_ch = min(samples.shape[1], N_CHANNELS)
            self._update_channel_display(actual_ch)
            self.filter_ctrl.set_n_channels(actual_ch)
            self._st_ch.setText(f'Ch: {actual_ch}')
        filtered = self.filter_ctrl.apply(samples)

        n_ch = min(samples.shape[1], N_CHANNELS)
        padded = np.zeros((filtered.shape[0], N_CHANNELS))
        padded[:, :n_ch] = filtered[:, :n_ch]
        t = ts.reshape(-1, 1)
        d = np.hstack((t, padded))

        # Ring buffers: O(1) append, no array copies in the hot path
        self._wave_buf.append(d)
        self._spec_buf.append(d)
        self._dirty_wave = True
        self._pkt_count += 1
        # LSL latency: sample timestamp → receive time
        t_receive = pylsl.local_clock()
        latencies_ms = (t_receive - ts) * 1000.0
        self._latency_ms = float(latencies_ms[-1])
        self._latency_history.append(self._latency_ms)
        self._latency_mean_ms = float(np.mean(self._latency_history))
        self._latency_max_ms = float(np.max(self._latency_history))

    def _on_ch_toggle(self, ch, checked):
        """Channel button toggled — collapse/expand plot and force refresh."""
        self._ts_plots[ch].setVisible(checked)
        self._dirty_wave = True

    # ==================================================================
    # Waveform render — per-channel subplots, 5s rolling window
    #   Y-axis: y_min … y_max + 15 % peak-to-peak margin, updated 500 ms.
    # ==================================================================
    def _render_wave(self):
        data = self._wave_buf.read()
        if not self._dirty_wave or data.shape[0] < 2:
            return
        self._dirty_wave = False
        abs_x = data[:, 0]
        t_now = abs_x[-1]
        t_cutoff = t_now - self.WINDOW_SECS

        mask = abs_x >= t_cutoff
        if not mask.any():
            return
        rel_x = abs_x[mask] - t_now

        do_y = (self._y_tick % 10 == 0)  # every 10th frame = 500 ms
        self._y_tick += 1

        for ch in range(N_CHANNELS):
            if not self._ts_plots[ch].isVisible():
                continue
            y = data[mask, ch + 1]
            self._ts_curves[ch].setData(x=rel_x, y=y)
            self._ts_plots[ch].setXRange(-self.WINDOW_SECS, 0)

            if do_y and y.size:
                ymin, ymax = float(y.min()), float(y.max())
                margin = (ymax - ymin) * 0.15 if ymax > ymin else 1.0
                self._ts_plots[ch].setYRange(ymin - margin, ymax + margin)

    # ==================================================================
    # FFT update (background thread — non-blocking)
    # ==================================================================
    def _on_psd_tick(self):
        # Apply previous background result if ready
        if self._psd_result is not None:
            with self._psd_lock:
                result = self._psd_result
                self._psd_result = None
            if result:
                for ch, (f, amp) in result:
                    if f is not None:
                        self._fft_curves[ch].setData(x=f, y=amp)
                        self._fft_curves[ch].show()
                    else:
                        self._fft_curves[ch].hide()

        # Launch new background computation if idle
        if not self._psd_busy:
            seg, actual_fs = self._get_spec_segment()
            if seg is not None:
                self._psd_busy = True
                threading.Thread(target=self._compute_psd,
                                 args=(seg, actual_fs), daemon=True).start()

    def _get_spec_segment(self):
        """Extract the last 4 s of spec data for PSD."""
        data = self._spec_buf.read()
        if data.shape[0] < 64:
            return None, None
        abs_x = data[:, 0]
        cut = abs_x[-1] - 3.0
        keep = abs_x >= cut
        if keep.sum() < 64:
            return None, None
        seg = data[keep, 1:]
        ts_seg = abs_x[keep]
        actual_fs = self._active_signal_srate
        if ts_seg[-1] > ts_seg[0]:
            actual_fs = float((len(ts_seg) - 1) / (ts_seg[-1] - ts_seg[0]))
        return seg, actual_fs

    def _compute_psd(self, seg, actual_fs):
        """Run welch() in background thread — does NOT touch GUI."""
        nperseg = min(512, len(seg))
        if nperseg < 16:
            self._psd_busy = False
            return
        nch = self._actual_ch
        results = []
        for ch in range(N_CHANNELS):
            if ch < nch and self._fft_btns[ch].isChecked():
                try:
                    f, psd = welch(seg[:, ch], fs=actual_fs, nperseg=nperseg,
                                   noverlap=nperseg // 2)
                    amp_uv = np.sqrt(np.maximum(psd, 1e-16))
                    results.append((ch, (f, amp_uv + 3.0 * ch)))
                except Exception:
                    results.append((ch, (None, None)))
            else:
                results.append((ch, (None, None)))
        with self._psd_lock:
            self._psd_result = results
        self._psd_busy = False

    # ==================================================================
    # Filters
    # ==================================================================
    def _on_hp_check(self, c):
        self.hp_spin.setEnabled(c)
        self._apply_filters()

    def _on_lp_check(self, c):
        self.lp_spin.setEnabled(c)
        self._apply_filters()

    def _on_notch_changed(self, idx):
        self.notch_bw.setEnabled(idx != 0)
        self._apply_filters()

    def _apply_filters(self):
        notch_map = {0: None, 1: 50.0, 2: 60.0}
        freq = notch_map.get(self.notch_combo.currentIndex())
        self.filter_ctrl.set_hp(self.hp_check.isChecked(), self.hp_spin.value())
        self.filter_ctrl.set_lp(self.lp_check.isChecked(), self.lp_spin.value())
        if freq is not None:
            bw = self.notch_bw.value()
            q = freq / bw if bw > 0 else 30.0
            self.filter_ctrl.set_notch(True, freq, q)
        else:
            self.filter_ctrl.set_notch(False)

    # ==================================================================
    # Cleanup
    # ==================================================================
    def closeEvent(self, event):
        r = QMessageBox.question(self, 'Window Close', '确定要关闭吗?',
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self._disconnect_internal()
            self.receiver.stop()
            self.lrc.terminate()
            event.accept()
        else:
            event.ignore()
