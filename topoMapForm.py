# -*- coding: utf-8 -*-
"""
TopoMapForm —— 头皮拓扑图窗口

集成 10-20 系统电极位置，支持两种可视化模式：
  1. 信号质量模式 —— 各通道标准差（μV）映射为颜色
  2. 功率分布模式 —— 指定频段功率（dB）的空间插值

使用 matplotlib + scipy.griddata 实现，不依赖 MNE。
"""

import numpy as np
from scipy.interpolate import griddata
from scipy import signal as scipy_signal

import matplotlib
matplotlib.use('Qt5Agg')
# ---- 中文字体支持 ----
import matplotlib.font_manager as fm
import warnings
_cjk_candidates = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Zen Hei',
                   'Noto Sans CJK SC', 'PingFang SC', 'AR PL UMing CN']
_available = [f.name for f in fm.fontManager.ttflist if f.name in _cjk_candidates]
if _available:
    matplotlib.rcParams['font.sans-serif'] = _available + ['DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore', message='Glyph.*missing from font')
# ------------------------
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.patches import Circle, Wedge
from matplotlib.path import Path
import matplotlib.patches as mpatches

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QSplitter, QVBoxLayout, QHBoxLayout,
    QComboBox, QLabel, QPushButton, QWidget, QSizePolicy,
)
from PyQt5.QtCore import QSettings, QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication

from lsl_config import FS


# ============================================================
# 64 通道 10-20 扩展系统电极名称和 2D 投影坐标
# 坐标归一化到单位圆（半径 ≈ 1），鼻尖方向为 +y，左耳为 -x
# ============================================================
_ELEC_NAMES_64 = [
    'Fp1','Fpz','Fp2',
    'AF7','AF3','AFz','AF4','AF8',
    'F9','F7','F5','F3','F1','Fz','F2','F4','F6','F8','F10',
    'FT7','FC5','FC3','FC1','FCz','FC2','FC4','FC6','FT8',
    'T7','C5','C3','C1','Cz','C2','C4','C6','T8',
    'TP7','CP5','CP3','CP1','CPz','CP2','CP4','CP6','TP8',
    'P7','P5','P3','P1','Pz','P2','P4','P6','P8',
    'PO7','PO3','POz','PO4','PO8',
    'O1','Oz','O2','Iz',
]

# 坐标：极坐标 (r, theta_deg) → 笛卡尔 (x, y)，theta=0° 指向鼻尖方向 (+y)
def _polar_to_xy(r, theta_deg):
    t = np.deg2rad(theta_deg)
    return (r * np.sin(t), r * np.cos(t))

_ELEC_COORDS_64 = np.array([
    # Row 1: frontal pole
    _polar_to_xy(0.90, -72),  # Fp1
    _polar_to_xy(0.95,   0),  # Fpz
    _polar_to_xy(0.90,  72),  # Fp2
    # Row 2: AF
    _polar_to_xy(0.78, -65),  # AF7
    _polar_to_xy(0.80, -27),  # AF3
    _polar_to_xy(0.82,   0),  # AFz
    _polar_to_xy(0.80,  27),  # AF4
    _polar_to_xy(0.78,  65),  # AF8
    # Row 3: F
    _polar_to_xy(0.55, -98),  # F9
    _polar_to_xy(0.60, -90),  # F7
    _polar_to_xy(0.60, -60),  # F5
    _polar_to_xy(0.60, -34),  # F3
    _polar_to_xy(0.60, -14),  # F1
    _polar_to_xy(0.62,   0),  # Fz
    _polar_to_xy(0.60,  14),  # F2
    _polar_to_xy(0.60,  34),  # F4
    _polar_to_xy(0.60,  60),  # F6
    _polar_to_xy(0.60,  90),  # F8
    _polar_to_xy(0.55,  98),  # F10
    # Row 4: FT/FC
    _polar_to_xy(0.42, -85),  # FT7
    _polar_to_xy(0.42, -57),  # FC5
    _polar_to_xy(0.42, -32),  # FC3
    _polar_to_xy(0.42, -13),  # FC1
    _polar_to_xy(0.44,   0),  # FCz
    _polar_to_xy(0.42,  13),  # FC2
    _polar_to_xy(0.42,  32),  # FC4
    _polar_to_xy(0.42,  57),  # FC6
    _polar_to_xy(0.42,  85),  # FT8
    # Row 5: T/C
    _polar_to_xy(0.23, -90),  # T7
    _polar_to_xy(0.23, -54),  # C5
    _polar_to_xy(0.23, -30),  # C3
    _polar_to_xy(0.23, -12),  # C1
    _polar_to_xy(0.00,   0),  # Cz
    _polar_to_xy(0.23,  12),  # C2
    _polar_to_xy(0.23,  30),  # C4
    _polar_to_xy(0.23,  54),  # C6
    _polar_to_xy(0.23,  90),  # T8
    # Row 6: TP/CP
    _polar_to_xy(0.42, -95),  # TP7
    _polar_to_xy(0.42, -123), # CP5
    _polar_to_xy(0.42, -148), # CP3
    _polar_to_xy(0.42, -167), # CP1
    _polar_to_xy(0.44, 180),  # CPz
    _polar_to_xy(0.42, 167),  # CP2
    _polar_to_xy(0.42, 148),  # CP4
    _polar_to_xy(0.42, 123),  # CP6
    _polar_to_xy(0.42,  95),  # TP8
    # Row 7: P
    _polar_to_xy(0.60, -90),  # P7
    _polar_to_xy(0.60, -120), # P5
    _polar_to_xy(0.60, -146), # P3
    _polar_to_xy(0.60, -166), # P1
    _polar_to_xy(0.62, 180),  # Pz
    _polar_to_xy(0.60, 166),  # P2
    _polar_to_xy(0.60, 146),  # P4
    _polar_to_xy(0.60, 120),  # P6
    _polar_to_xy(0.60,  90),  # P8
    # Row 8: PO
    _polar_to_xy(0.78, -115), # PO7
    _polar_to_xy(0.80, -153), # PO3
    _polar_to_xy(0.82, 180),  # POz
    _polar_to_xy(0.80, 153),  # PO4
    _polar_to_xy(0.78, 115),  # PO8
    # Row 9: occipital
    _polar_to_xy(0.90, -108), # O1
    _polar_to_xy(0.95, 180),  # Oz
    _polar_to_xy(0.90, 108),  # O2
    _polar_to_xy(0.98, 180),  # Iz
], dtype=np.float64)


class TopoMapForm(QtWidgets.QWidget):
    """头皮拓扑图窗口 —— 信号质量 / 功率空间分布"""

    BANDS = {
        'Delta': (0.5, 4),
        'Theta': (4, 8),
        'Alpha': (8, 13),
        'Beta':  (13, 30),
        'Gamma': (30, 45),
    }

    # 信号质量阈值 (μV std)
    SQ_GOOD = 100.0
    SQ_WARN = 300.0

    # 标志性电极（加粗高亮）
    _KEY_ELECS = {'Fpz','Fz','Cz','Pz','Oz','T7','T8','F7','F8','P7','P8','O1','O2'}

    def __init__(self, impf=None, bpf=None):
        super().__init__()
        self.setWindowTitle("头皮拓扑图")
        self.setMinimumSize(480, 520)

        self._impf = impf  # ImpedanceForm 引用（共享信号质量数据）
        self._bpf = bpf    # BandpowerForm 引用（共享频段功率数据）

        self._mode = 'quality'     # 'quality' | 'power'
        self._band = 'Alpha'
        self._update_hz = 2        # 每秒刷新 2 次
        self._buffer_secs = 2.0
        self._max_buffer = int(FS * self._buffer_secs)

        # 数据缓冲区（仅在共享数据不可用时用于自计算）
        self._data_buf = np.empty((0, 64), dtype=np.float64)
        self._ts_buf = np.empty((0,), dtype=np.float64)

        # 缓存最新计算结果
        self._latest_std = np.zeros(64, dtype=np.float64)
        self._latest_powers = {b: np.zeros(64, dtype=np.float64) for b in self.BANDS}
        self._has_data = False

        self._build_ui()
        self._start_timer()
        self._init_settings()
        self._draw_initial()

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        # ---- matplotlib figure ----
        self._fig = Figure(figsize=(5, 5), dpi=90)
        self._fig.set_facecolor('#2d2d2d')
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---- 控制栏 ----
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QLabel("模式:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["信号质量", "功率分布"])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ctrl.addWidget(self._mode_combo)

        ctrl.addWidget(QLabel("频段:"))
        self._band_combo = QComboBox()
        self._band_combo.addItems(list(self.BANDS.keys()))
        self._band_combo.setCurrentText(self._band)
        self._band_combo.currentTextChanged.connect(self._on_band_changed)
        ctrl.addWidget(self._band_combo)

        ctrl.addStretch()

        self._info_label = QLabel("等待数据…")
        self._info_label.setStyleSheet("color: #aaa;")
        ctrl.addWidget(self._info_label)

        ctrl_widget = QWidget()
        ctrl_widget.setLayout(ctrl)

        # ---- 布局 ----
        splitter = QSplitter(Qt.Vertical)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self._canvas)
        splitter.addWidget(top)
        splitter.addWidget(ctrl_widget)
        splitter.setSizes([460, 40])

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.addWidget(splitter)

        self._update_band_visibility()

    # --------------------------------------------------------
    # QSettings
    # --------------------------------------------------------
    def _init_settings(self):
        self._settings = QSettings('./topoMapFormSetting.ini', QSettings.IniFormat)
        self.resize(self._settings.value("size", QSize(520, 560)))
        pos = self._settings.value("pos")
        size = self._settings.value("size")
        if pos is not None and size is not None:
            screen = QApplication.primaryScreen().geometry()
            if pos.x() < screen.width() - 100 and pos.y() < screen.height() - 100:
                self.move(pos)

    # --------------------------------------------------------
    # 定时器
    # --------------------------------------------------------
    def _start_timer(self):
        interval = int(1000 / self._update_hz)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(interval)

    def _tick(self):
        # 优先使用共享数据（避免重复 FFT/Welch），不可用时回退到自计算
        if not self._try_shared_data():
            if not self._has_data:
                return
            self._compute_metrics()
        self._draw()

    # --------------------------------------------------------
    # 数据接口 (由 Controller._on_ui_data 调用)
    # --------------------------------------------------------
    def deal_with_data_inlet(self, ts, arr):
        if arr.shape[1] == 1:
            arr = np.hstack((arr, np.zeros((arr.shape[0], 63))))
        self._data_buf = np.concatenate((self._data_buf, arr), axis=0)
        self._ts_buf = np.concatenate((self._ts_buf, ts), axis=0)
        # 按时间裁剪
        cutoff = self._ts_buf[-1] - self._buffer_secs
        keep = self._ts_buf >= cutoff
        if not np.all(keep):
            idx = np.argmax(keep)
            self._data_buf = self._data_buf[idx:, :]
            self._ts_buf = self._ts_buf[idx:]
        self._has_data = True

    # --------------------------------------------------------
    # 指标计算
    # --------------------------------------------------------
    def _try_shared_data(self):
        """尝试从 ImpedanceForm / BandpowerForm 获取已计算数据，避免重复 FFT"""
        if self._mode == 'quality' and self._impf is not None:
            std = self._impf.get_signal_quality()
            if std is not None:
                self._latest_std = std
                self._has_data = True
                return True
        elif self._mode == 'power' and self._bpf is not None:
            powers = self._bpf.get_band_power(self._band)
            if powers is not None:
                self._latest_powers[self._band] = powers
                self._has_data = True
                return True
        return False

    def _compute_metrics(self):
        """自计算（仅在共享数据不可用时使用）"""
        data = self._data_buf
        if data.shape[0] < 32:
            return

        # 信号质量模式：只需标准差
        self._latest_std = np.std(data, axis=0, ddof=1)
        if self._mode == 'quality':
            return

        # 功率分布模式：只计算当前选中频段
        lo, hi = self.BANDS[self._band]
        nperseg = min(128, data.shape[0])
        noverlap = min(64, data.shape[0] // 2)
        powers = np.zeros(64, dtype=np.float64)
        for ch in range(64):
            f, psd = scipy_signal.welch(
                data[:, ch], fs=FS, nperseg=nperseg,
                noverlap=noverlap, axis=-1
            )
            mask = (f >= lo) & (f < hi)
            if mask.any():
                powers[ch] = np.trapz(psd[mask], f[mask])
        self._latest_powers[self._band] = powers

    # --------------------------------------------------------
    # 绘图
    # --------------------------------------------------------
    def _draw_initial(self):
        """启动时绘制头部轮廓和电极位置（无数据，灰色电极）"""
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.set_facecolor('#2d2d2d')
        self._draw_head_outline(ax)
        self._draw_electrodes_no_data(ax)
        ax.set_title("头皮拓扑图 — 等待数据…", color='white', fontsize=11, pad=2)
        ax.axis('equal')
        ax.axis('off')
        self._fig.tight_layout(pad=0.5, rect=[0, 0, 1, 0.93])
        self._canvas.draw()

    def _draw_electrodes_no_data(self, ax):
        """仅绘制电极位置散点（无插值，灰色，关键电极高亮）"""
        coords = _ELEC_COORDS_64
        names = _ELEC_NAMES_64
        is_key = np.array([n in self._KEY_ELECS for n in names])
        # 普通电极
        ax.scatter(coords[~is_key, 0], coords[~is_key, 1], c='#555555', s=14,
                   edgecolors='white', linewidths=0.4, zorder=3)
        # 标志性电极（更大、更亮）
        ax.scatter(coords[is_key, 0], coords[is_key, 1], c='#888888', s=40,
                   edgecolors='white', linewidths=1.2, zorder=4)
        for i, name in enumerate(names):
            if is_key[i]:
                ax.annotate(name, (coords[i, 0], coords[i, 1]),
                           textcoords="offset points", xytext=(0, -13),
                           fontsize=6, color='white', ha='center', zorder=5)

    def _draw(self):
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.set_facecolor('#2d2d2d')

        if self._mode == 'quality':
            data = self._latest_std.copy()
            title = "信号质量 (标准差 μV)"
            cmap_name = 'RdYlGn_r'
            vmin, vmax = 0.0, 400.0
        else:
            raw_db = 10.0 * np.log10(np.maximum(self._latest_powers[self._band], 1e-12))
            # 动态 dB 范围：取 5%-95% 百分位，最小跨度 20 dB
            finite = raw_db[np.isfinite(raw_db)]
            if len(finite) > 4:
                lo, hi = np.percentile(finite, [5, 95])
                span = hi - lo
                if span < 20:
                    mid = (lo + hi) / 2.0
                    lo, hi = mid - 10.0, mid + 10.0
                lo, hi = np.floor(lo), np.ceil(hi)
            else:
                lo, hi = -25.0, 35.0
            data = raw_db
            title = f"{self._band} 功率 (dB)"
            cmap_name = 'viridis'
            vmin, vmax = lo, hi

        self._draw_head_outline(ax)
        self._draw_electrodes(ax, data, cmap_name, vmin, vmax)
        self._draw_colorbar(ax, vmin, vmax, cmap_name, title)
        ax.set_title(title, color='white', fontsize=11, pad=2)
        ax.axis('equal')
        ax.axis('off')
        self._fig.tight_layout(pad=0.5, rect=[0, 0, 1, 0.93])
        self._canvas.draw()

        # 更新信息标签
        if self._mode == 'quality':
            bad = int(np.sum(self._latest_std > self.SQ_WARN))
            warn = int(np.sum((self._latest_std > self.SQ_GOOD) & (self._latest_std <= self.SQ_WARN)))
            self._info_label.setText(
                f"良好: {64 - bad - warn}  |  警告: {warn}  |  异常: {bad}"
            )
        else:
            self._info_label.setText(f"频段: {self._band}  |  范围: {self.BANDS[self._band][0]}-{self.BANDS[self._band][1]} Hz")

    # --------------------------------------------------------
    # 头部轮廓 + 鼻子 + 耳朵
    # --------------------------------------------------------
    def _draw_head_outline(self, ax):
        head = Circle((0, 0), 1.02, fill=False, edgecolor='white', linewidth=1.5, zorder=1)
        ax.add_patch(head)
        # 鼻子（顶部三角）
        nose = np.array([[-0.08, 1.02], [0.0, 1.14], [0.08, 1.02]])
        ax.add_patch(mpatches.Polygon(nose, closed=True, fill=True,
                                       facecolor='white', edgecolor='white', linewidth=1, zorder=1))
        # 耳朵（左右）
        for ear_x, ear_dir in [(-1.02, -1), (1.02, 1)]:
            ear = Wedge((ear_x, 0), 0.12, 210, 330, fill=True,
                        facecolor='white', edgecolor='white', linewidth=1, zorder=1)
            ax.add_patch(ear)

    # --------------------------------------------------------
    # 电极散点 + 插值等值线
    # --------------------------------------------------------
    def _draw_electrodes(self, ax, data, cmap_name, vmin, vmax):
        coords = _ELEC_COORDS_64
        cmap = matplotlib.cm.get_cmap(cmap_name)

        # 空间插值 (griddata)
        grid_x, grid_y = np.mgrid[-1.1:1.1:120j, -1.1:1.1:120j]
        grid_z = griddata(coords, data, (grid_x, grid_y), method='cubic')
        # 用最近邻填充边缘 NaN
        if np.any(np.isnan(grid_z)):
            grid_z_nn = griddata(coords, data, (grid_x, grid_y), method='nearest')
            grid_z = np.where(np.isnan(grid_z), grid_z_nn, grid_z)

        # 蒙版：仅头部圆形内部
        mask = (grid_x ** 2 + grid_y ** 2) > 1.02 ** 2
        grid_z = np.ma.masked_where(mask, grid_z)

        # 等值线填充
        ax.contourf(grid_x, grid_y, grid_z, levels=40, cmap=cmap_name,
                    vmin=vmin, vmax=vmax, zorder=2)

        # 电极位置散点
        norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
        colors = cmap(norm(np.clip(data, vmin, vmax)))
        names = _ELEC_NAMES_64
        is_key = np.array([n in self._KEY_ELECS for n in names])
        # 普通电极
        ax.scatter(coords[~is_key, 0], coords[~is_key, 1], c=colors[~is_key], s=14,
                   edgecolors='white', linewidths=0.4, zorder=3)
        # 标志性电极（更大，带白色外圈）
        ax.scatter(coords[is_key, 0], coords[is_key, 1], c=colors[is_key], s=44,
                   edgecolors='white', linewidths=1.5, zorder=4)
        # 通道标签（仅标志性电极）
        for i, name in enumerate(names):
            if is_key[i]:
                ax.annotate(name, (coords[i, 0], coords[i, 1]),
                           textcoords="offset points", xytext=(0, -13),
                           fontsize=6, color='white', ha='center', zorder=5)

    # --------------------------------------------------------
    # 颜色条
    # --------------------------------------------------------
    def _draw_colorbar(self, ax, vmin, vmax, cmap_name, title):
        import matplotlib.pyplot as plt
        sm = plt.cm.ScalarMappable(
            cmap=cmap_name,
            norm=matplotlib.colors.Normalize(vmin=vmin, vmax=vmax),
        )
        sm.set_array([])
        cbar = self._fig.colorbar(sm, ax=ax, shrink=0.72, pad=0.02)
        cbar.ax.yaxis.set_tick_params(color='white', labelsize=7)
        cbar.outline.set_edgecolor('white')
        for label in cbar.ax.get_yticklabels():
            label.set_color('white')
        if self._mode == 'quality':
            cbar.set_label('μV', color='white', fontsize=8)
        else:
            cbar.set_label('dB', color='white', fontsize=8)

    # --------------------------------------------------------
    # 模式 / 频段切换
    # --------------------------------------------------------
    def _on_mode_changed(self, idx):
        self._mode = 'quality' if idx == 0 else 'power'
        self._update_band_visibility()
        if self._has_data:
            self._compute_metrics()
            self._draw()

    def _on_band_changed(self, name):
        self._band = name
        if self._has_data:
            self._compute_metrics()
            self._draw()

    def _update_band_visibility(self):
        self._band_combo.setVisible(self._mode == 'power')

    # --------------------------------------------------------
    # 窗口生命周期
    # --------------------------------------------------------
    def set_playback_mode(self, active):
        """回放期间暂停内部拓扑图定时器，避免重复计算导致卡顿"""
        if active:
            self._timer.stop()
        else:
            self._timer.start(int(1000 / self._update_hz))

    def reset_view(self):
        if self._timer.isActive():
            self._timer.stop()
        self._data_buf = np.empty((0, 64), dtype=np.float64)
        self._ts_buf = np.empty((0,), dtype=np.float64)
        self._has_data = False
        self._fig.clear()
        self._canvas.draw()
        self._timer.start(int(1000 / self._update_hz))

    def closeEvent(self, e):
        self._timer.stop()
        self._settings.setValue("size", self.size())
        self._settings.setValue("pos", self.pos())
        e.accept()

    def close_win(self):
        self._settings.setValue("size", self.size())
        self._settings.setValue("pos", self.pos())
        self.close()
