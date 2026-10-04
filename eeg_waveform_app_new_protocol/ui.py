from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.Qt import Qt

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QMessageBox

import matplotlib

matplotlib.use('Qt5Agg')

from PyQt5.QtWidgets import QApplication

import constantValues as cv
import debugPrinter as dp
from PyQt5.QtCore import QSettings, QPoint, QSize
from PyQt5.QtWidgets import QInputDialog, QLineEdit
import os


qt_creator_file = os.path.join(os.path.dirname(__file__), "ui_config", "mainwindow.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(qt_creator_file)
ini_file = os.path.join(os.path.dirname(__file__), "ui_config", "uiSetting.ini")


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    evt_win = pyqtSignal(str, str)

    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)

        # 初始化变量
        self.bridge_process = None
        self.cf = None
        self.sf = None
        self.controller = None

        # ========== 修改按钮文字 ==========
        self.btn_open_com.setText("开始记录")
        self.btn_close_com.setText("停止记录")

        # 暂停显示按钮已废弃，隐藏
        self.btn_stop_disconnect.hide()

        # ========== 创建"数据记录" GroupBox ==========
        data_group = QtWidgets.QGroupBox("数据记录")
        data_layout = QtWidgets.QVBoxLayout(data_group)

        # 1. 路径选择行
        path_widget = QtWidgets.QWidget()
        path_layout = QtWidgets.QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)

        path_label = QtWidgets.QLabel("保存路径:")
        self.path_line_edit = QtWidgets.QLineEdit()
        self.path_line_edit.setReadOnly(True)
        self.path_line_edit.setText("./data")
        #self.path_line_edit.setFixedWidth(200)
        self.path_line_edit.setPlaceholderText("请选择保存目录")

        self.path_line_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        browse_btn = QtWidgets.QPushButton("📁")
        browse_btn.setFixedSize(35, 28)
        browse_btn.setToolTip("选择保存路径")
        browse_btn.clicked.connect(self.browse_save_path)

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_line_edit)
        path_layout.addWidget(browse_btn)
        #path_layout.addStretch()

        # 3. 按钮行
        button_widget = QtWidgets.QWidget()
        button_layout = QtWidgets.QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_open_com.setMinimumWidth(120)
        self.btn_open_com.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.btn_close_com.setMinimumWidth(120)
        self.btn_close_com.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        button_layout.addWidget(self.btn_open_com)
        button_layout.addStretch(1)
        button_layout.addWidget(self.btn_close_com)

        data_layout.addWidget(path_widget)
        data_layout.addWidget(button_widget)

        # 4. 手动标记行
        marker_widget = QtWidgets.QWidget()
        marker_layout = QtWidgets.QHBoxLayout(marker_widget)
        marker_layout.setContentsMargins(0, 0, 0, 0)

        marker_layout.addWidget(QtWidgets.QLabel("事件标记:"))
        self.marker_combo = QtWidgets.QComboBox()
        self.marker_combo.addItems(['artifact', 'movement', 'blink', 'instruction', 'rest_start', 'rest_end', 'custom'])
        self.marker_combo.setMinimumWidth(110)
        self.marker_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        marker_layout.addWidget(self.marker_combo, 1)

        self.marker_custom_edit = QtWidgets.QLineEdit()
        self.marker_custom_edit.setPlaceholderText("自定义标签")
        self.marker_custom_edit.setMinimumWidth(100)
        self.marker_custom_edit.setVisible(False)
        marker_layout.addWidget(self.marker_custom_edit, 1)

        self.marker_combo.currentTextChanged.connect(lambda t: self.marker_custom_edit.setVisible(t == 'custom'))

        self.btn_insert_marker = QtWidgets.QPushButton("插入标记")
        self.btn_insert_marker.setMinimumWidth(70)
        self.btn_insert_marker.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.btn_insert_marker.clicked.connect(self._on_insert_marker)
        marker_layout.addWidget(self.btn_insert_marker)

        self.marker_widget = marker_widget

        central_widget = self.centralWidget()
        layout = central_widget.layout()
        if layout:
            layout.insertWidget(0, data_group)
        # =================================================

        # ========== 滤波器 GroupBox ==========
        filter_group = QtWidgets.QGroupBox("滤波器设置")
        filter_layout = QtWidgets.QGridLayout(filter_group)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setHorizontalSpacing(8)
        filter_layout.setVerticalSpacing(6)

        # --- Row 0: 高通 + 低通 ---
        hp_label = QtWidgets.QLabel("高通 (HP):")
        filter_layout.addWidget(hp_label, 0, 0)
        self.hp_check = QtWidgets.QCheckBox()
        self.hp_check.setChecked(True)
        self.hp_check.setToolTip("启用/关闭高通滤波")
        self.hp_check.toggled.connect(self._on_hp_check)
        filter_layout.addWidget(self.hp_check, 0, 1)
        self.hp_spin = QtWidgets.QDoubleSpinBox()
        self.hp_spin.setRange(0.1, 30.0)
        self.hp_spin.setSingleStep(0.1)
        self.hp_spin.setDecimals(1)
        self.hp_spin.setValue(0.5)
        self.hp_spin.setSuffix(" Hz")
        self.hp_spin.setMinimumWidth(80)
        self.hp_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.hp_spin.valueChanged.connect(self._on_hp_changed)
        filter_layout.addWidget(self.hp_spin, 0, 2)

        lp_label = QtWidgets.QLabel("低通 (LP):")
        filter_layout.addWidget(lp_label, 0, 3)
        self.lp_check = QtWidgets.QCheckBox()
        self.lp_check.setChecked(True)
        self.lp_check.setToolTip("启用/关闭低通滤波")
        self.lp_check.toggled.connect(self._on_lp_check)
        filter_layout.addWidget(self.lp_check, 0, 4)
        self.lp_spin = QtWidgets.QDoubleSpinBox()
        self.lp_spin.setRange(15.0, 120.0)
        self.lp_spin.setSingleStep(1.0)
        self.lp_spin.setDecimals(0)
        self.lp_spin.setValue(40.0)
        self.lp_spin.setSuffix(" Hz")
        self.lp_spin.setMinimumWidth(80)
        self.lp_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.lp_spin.valueChanged.connect(self._on_lp_changed)
        filter_layout.addWidget(self.lp_spin, 0, 5)

        # --- Row 1: 陷波 + 带宽 ---
        notch_label = QtWidgets.QLabel("陷波 (Notch):")
        filter_layout.addWidget(notch_label, 1, 0)
        self.notch_combo = QtWidgets.QComboBox()
        self.notch_combo.addItems(["Off", "50 Hz", "60 Hz"])
        self.notch_combo.setCurrentIndex(1)
        self.notch_combo.setMinimumWidth(70)
        self.notch_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.notch_combo.currentIndexChanged.connect(self._on_notch_changed)
        filter_layout.addWidget(self.notch_combo, 1, 1, 1, 2)

        bw_label = QtWidgets.QLabel("带宽 ±")
        filter_layout.addWidget(bw_label, 1, 3)
        self.notch_bw_spin = QtWidgets.QDoubleSpinBox()
        self.notch_bw_spin.setRange(0.5, 10.0)
        self.notch_bw_spin.setSingleStep(0.5)
        self.notch_bw_spin.setDecimals(1)
        self.notch_bw_spin.setValue(1.0)
        self.notch_bw_spin.setSuffix(" Hz")
        self.notch_bw_spin.setMinimumWidth(70)
        self.notch_bw_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.notch_bw_spin.valueChanged.connect(self._on_notch_bw_changed)
        filter_layout.addWidget(self.notch_bw_spin, 1, 4, 1, 2)

        filter_layout.setColumnStretch(0, 0)
        filter_layout.setColumnStretch(1, 0)
        filter_layout.setColumnStretch(2, 1)
        filter_layout.setColumnStretch(3, 0)
        filter_layout.setColumnStretch(4, 0)
        filter_layout.setColumnStretch(5, 1)

        if layout:
            layout.insertWidget(1, filter_group)
        # =================================================

        # ========== 双列日志区域 ==========
        central_layout = self.centralWidget().layout()
        if central_layout is not None:
            # 找到原来 textBrowser_evt_log 在布局中的位置
            old_log_idx = -1
            for i in range(central_layout.count()):
                item = central_layout.itemAt(i)
                if item and item.widget() is self.textBrowser_evt_log:
                    old_log_idx = i
                    break
            if old_log_idx >= 0:
                central_layout.removeWidget(self.textBrowser_evt_log)
                self.textBrowser_evt_log.hide()

                # 创建水平分割器
                log_splitter = QtWidgets.QSplitter(Qt.Horizontal)
                log_splitter.setHandleWidth(5)

                # 左侧：硬件数据日志
                left_container = QtWidgets.QWidget()
                left_layout = QtWidgets.QVBoxLayout(left_container)
                left_layout.setContentsMargins(0, 0, 0, 0)
                left_layout.setSpacing(2)
                left_label = QtWidgets.QLabel("硬件数据")
                left_label.setStyleSheet("font-weight: bold; padding-left: 4px;")
                self.textBrowser_data_log = QtWidgets.QTextBrowser()
                self.textBrowser_data_log.setReadOnly(True)
                self.textBrowser_data_log.document().setMaximumBlockCount(500)
                left_layout.addWidget(left_label)
                left_layout.addWidget(self.textBrowser_data_log)

                # 右侧：功能状态日志
                right_container = QtWidgets.QWidget()
                right_layout = QtWidgets.QVBoxLayout(right_container)
                right_layout.setContentsMargins(0, 0, 0, 0)
                right_layout.setSpacing(2)
                right_label = QtWidgets.QLabel("功能状态")
                right_label.setStyleSheet("font-weight: bold; padding-left: 4px;")
                self.textBrowser_evt_log = QtWidgets.QTextBrowser()
                self.textBrowser_evt_log.setReadOnly(True)
                self.textBrowser_evt_log.document().setMaximumBlockCount(500)
                right_layout.addWidget(right_label)
                right_layout.addWidget(self.textBrowser_evt_log)

                log_splitter.addWidget(left_container)
                log_splitter.addWidget(right_container)
                log_splitter.setSizes([200, 200])

                central_layout.insertWidget(old_log_idx, log_splitter)
        # ===================================


        # ========== 按钮信号连接 ==========
        self.btn_open_com.clicked.connect(self.open_com_btn_click)
        self.btn_close_com.clicked.connect(self.close_com_btn_click)
        self.btn_reconnect.clicked.connect(self.reconnect_btn_click)

        # ========== 重组控制面板布局为双行 ==========
        parent = self.btn_reconnect.parent()
        if parent and parent.layout():
            old_layout = parent.layout()
            while old_layout.count():
                old_layout.takeAt(0)

            container = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(container)
            grid.setContentsMargins(6, 6, 6, 6)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)

            # ==== Row 0: 事件标记 ====
            grid.addWidget(self.marker_widget, 0, 0, 1, 3)

            # ==== Row 1: 断开连接 | 重连 | 回放 ====
            self.btn_con_dev.setText("断开连接")
            self.btn_con_dev.setCheckable(True)
            self.btn_con_dev.setChecked(False)
            self.btn_con_dev.setMinimumWidth(80)
            self.btn_con_dev.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.btn_con_dev.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 14px;
                    min-width: 80px;
                    min-height: 30px;
                    padding-left: 8px;
                    padding-right: 8px;
                    background-color: #546E7A;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #C62828;
                    color: white;
                }
            """)
            self.btn_con_dev.toggled.connect(self._on_disconnect)
            grid.addWidget(self.btn_con_dev, 1, 0)

            self.btn_reconnect.setMinimumWidth(80)
            self.btn_reconnect.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.btn_reconnect.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 14px;
                    min-width: 80px;
                    min-height: 30px;
                    padding-left: 8px;
                    padding-right: 8px;
                    background-color: #546E7A;
                    color: white;
                    font-weight: bold;
                }
            """)
            grid.addWidget(self.btn_reconnect, 1, 1)

            self.btn_playback = QtWidgets.QPushButton("回放")
            self.btn_playback.setMinimumWidth(70)
            self.btn_playback.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.btn_playback.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    min-width: 70px;
                    min-height: 36px;
                    padding-left: 8px;
                    padding-right: 8px;
                    background-color: #00796B;
                    color: white;
                    font-weight: bold;
                }
            """)
            self.btn_playback.clicked.connect(self._on_playback)
            grid.addWidget(self.btn_playback, 1, 2)

            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(2, 1)

            self.groupBox_connect.setTitle("控制面板")

            old_layout.addWidget(container)


        self.setWindowTitle("BCI 上位机")
        self.setMinimumSize(520, 600)

        self.c = None

        self.settings = QSettings('./uiSetting.ini', QSettings.IniFormat)
        self.settings.remove("size")
        self.settings.remove("pos")
        self.resize(600, 720)
        if False:
            if (self.settings.value("pos") is not None) and (self.settings.value("size") is not None):
                screenRect = QApplication.primaryScreen().geometry()
                self.height = screenRect.height()
                if self.settings.value("pos").x() < (screenRect.width() - 100) and \
                        self.settings.value("pos").y() < (screenRect.height() - 100):
                    self.move(self.settings.value("pos", QPoint(50, 50)))

        dp.dpt("mainwindow construction")


    def kill_bridge_process(self):
        """（已废弃 — UDP 接收已集成到主进程）"""
        pass

    def _on_disconnect(self, checked: bool):
        """断开/恢复连接 — Toggle 按钮（不销毁后台线程，仅暂停/恢复数据拉取）"""
        if self.controller is None:
            return
        if checked:
            self.controller.pause_data()
            self.btn_con_dev.setText("恢复连接")
            self.log_info('已断开连接')
        else:
            self.controller.resume_data()
            self.btn_con_dev.setText("断开连接")
            self.log_info('已恢复连接')

    def recreate_controller(self):
        """（已废弃 — Controller 在 app.py 启动时创建）"""
        pass

    def reconnect_btn_click(self):
        """重连 - 打开设备配置网页"""
        import webbrowser
        webbrowser.open('http://192.168.4.1/')
        self.log_info('正在打开设备配置页面...')

    def open_com_btn_click(self, flag):
        """开始记录"""
        if self.controller is not None:
            self.controller.start_measurement()
        self.log_info('开始记录...')

    def close_com_btn_click(self):
        """停止记录"""
        if self.controller is not None:
            self.controller.stop_measurement()
        self.log_info('停止记录，数据已保存')

    def browse_save_path(self):
        """选择保存路径"""
        from PyQt5.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.path_line_edit.text())
        if path:
            self.path_line_edit.setText(path)
            if self.controller is not None:
                self.controller.save_path = path
            self.log_info(f"保存路径已设置为: {path}")

    def flash_led_triggered(self):
        dp.dpt('flash_led_triggered - - -')
        self.evt_win.emit(cv.SERIAL_CMD_FALSH_LED, cv.DUMMY_STR)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Q:
            self.close()

    def exit_app(self):
        self.close()

    def closeEvent(self, event):
        r = QMessageBox.question(self, "Window Close", "Are you sure to close?",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            if self.controller is not None:
                if hasattr(self.controller, 'udp') and self.controller.udp is not None:
                    self.controller.udp.stop()
            self.evt_win.emit(cv.EVT_WIN_QUIT, cv.DUMMY_STR)

            if self.cf is not None:
                self.cf.close()
                self.cf = None
            if self.sf is not None:
                self.sf.close()
                self.sf = None
            self.settings.setValue("size", self.size())
            self.settings.setValue("pos", self.pos())
            event.accept()
        else:
            event.ignore()

    def show_error(self, s):
        QMessageBox.warning(self, "error", s)

    def get_input_fileName(self, hint):
        text, ok = QInputDialog().getText(self, "File Name For Saving",
                                          "(you can use Subject Name or Session name):", QLineEdit.Normal, hint)
        return text, ok

    def add_serial_port_to_combox(self, li):
        pass

    def set_combox_item(self, s):
        pass

    def log_data(self, s: str):
        """硬件数据日志 —— 写入左侧 textBrowser_data_log，自动滚动到最新"""
        if s != cv.LOG_INFO_INGNORE:
            self.textBrowser_data_log.append(s)
            sb = self.textBrowser_data_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def log_info(self, s):
        """功能状态日志 —— 写入右侧 textBrowser_evt_log"""
        if s != cv.LOG_INFO_INGNORE:
            self.textBrowser_evt_log.append(s)

    def new_mac(self, s):
        pass

    def serial_cmd(self, cmd):
        if cmd == cv.EVT_SERIAL_OPEN_SUC:
            self.btn_open_com.setEnabled(False)
            self.btn_close_com.setEnabled(True)
        elif cmd == cv.EVT_SERIAL_OPEN_FAILED:
            #self.log_info('serial opend faild, check the device manager')
            pass
        elif cmd == cv.EVT_SERIAL_CLOSE_SUC:
            self.btn_open_com.setEnabled(True)
            self.btn_close_com.setEnabled(False)
            pass

    def _on_insert_marker(self):
        """插入手动事件标记"""
        if self.controller is None:
            return
        label = self.marker_combo.currentText()
        if label == 'custom':
            label = self.marker_custom_edit.text().strip()
            if not label:
                self.log_info('请输入自定义标记标签')
                return
        self.controller.insert_manual_marker(label)
        self.log_info(f'已插入标记: {label}')

    def _on_hp_check(self, checked):
        self.hp_spin.setEnabled(checked)
        self._apply_hp()

    def _on_hp_changed(self, val):
        if self.hp_check.isChecked():
            self._apply_hp()

    def _apply_hp(self):
        if self.controller is None:
            return
        if self.hp_check.isChecked():
            self.controller.set_highpass(self.hp_spin.value())
            self.log_info(f'高通滤波: {self.hp_spin.value():.1f} Hz')
        else:
            self.controller.set_highpass(None)
            self.log_info('高通滤波: Off')

    def _on_lp_check(self, checked):
        self.lp_spin.setEnabled(checked)
        self._apply_lp()

    def _on_lp_changed(self, val):
        if self.lp_check.isChecked():
            self._apply_lp()

    def _apply_lp(self):
        if self.controller is None:
            return
        if self.lp_check.isChecked():
            self.controller.set_lowpass(self.lp_spin.value())
            self.log_info(f'低通滤波: {self.lp_spin.value():.0f} Hz')
        else:
            self.controller.set_lowpass(None)
            self.log_info('低通滤波: Off')

    def _on_notch_changed(self, idx):
        self.notch_bw_spin.setEnabled(idx != 0)
        self._apply_notch()

    def _on_notch_bw_changed(self, val):
        if self.notch_combo.currentIndex() != 0:
            self._apply_notch()

    def _apply_notch(self):
        if self.controller is None:
            return
        notch_map = {0: None, 1: 50.0, 2: 60.0}
        freq = notch_map.get(self.notch_combo.currentIndex())
        if freq is not None:
            bw = self.notch_bw_spin.value()
            self.controller.set_notch(freq, bw)
            self.log_info(f'陷波滤波: {freq:.0f} Hz ± {bw:.1f} Hz')
        else:
            self.controller.set_notch(None)
            self.log_info('陷波滤波: Off')

    def _on_playback(self):
        """打开回放控制 —— 非模态文件对话框 + 后台线程加载，不阻塞主线程"""
        from PyQt5.QtWidgets import QFileDialog
        dlg = QFileDialog(self, "选择回放文件", "./data",
                          "EDF/CSV Files (*.edf *.csv);;All Files (*)")
        dlg.setFileMode(QFileDialog.ExistingFile)
        dlg.setAcceptMode(QFileDialog.AcceptOpen)
        dlg.fileSelected.connect(self._on_playback_file_selected)
        dlg.open()

    def _on_playback_file_selected(self, filepath):
        """文件选定后，启动后台线程加载数据"""
        if not filepath:
            return

        self.log_info(f'正在加载回放文件: {os.path.basename(filepath)}')

        from playback import PlaybackFileLoader, PlaybackController
        from PyQt5.QtCore import QThread

        # 创建控制器（数据稍后由 set_data 注入）
        self.playback_ctrl = PlaybackController(
            cf=self.cf, sf=self.sf,
            controller=self.controller
        )

        self._playback_filepath = filepath

        # 后台线程加载
        self._loader_worker = PlaybackFileLoader(filepath)
        self._loader_thread = QThread()
        self._loader_worker.moveToThread(self._loader_thread)
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.loaded.connect(self._on_playback_data_loaded)
        self._loader_worker.error.connect(self._on_playback_load_error)
        self._loader_worker.loaded.connect(self._loader_thread.quit)
        self._loader_worker.error.connect(self._loader_thread.quit)
        self._loader_thread.start()

    def _on_playback_data_loaded(self, data_eeg, data_ts):
        """后台加载完成，注入数据并显示回放面板"""
        self.playback_ctrl.set_data(data_eeg, data_ts)
        self._show_playback_panel(self._playback_filepath)
        self.log_info(f'回放文件加载完成 ({data_eeg.shape[0]} 采样点)')

    def _on_playback_load_error(self, msg):
        """后台加载失败"""
        self.log_info(f'回放文件加载失败: {msg}')
        self.playback_ctrl = None

    def _show_playback_panel(self, filepath):
        """显示回放控制面板"""
        panel = QtWidgets.QDialog(self)
        panel.setWindowTitle(f"回放: {os.path.basename(filepath)}")
        panel.resize(400, 200)

        layout = QtWidgets.QVBoxLayout(panel)

        # 文件路径
        layout.addWidget(QtWidgets.QLabel(f"文件: {os.path.basename(filepath)}"))

        # 进度条
        self.playback_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.playback_slider.setRange(0, 100)
        self.playback_slider.setValue(0)
        self.playback_slider.sliderMoved.connect(
            lambda v: self.playback_ctrl.seek(v / 100.0)
        )
        layout.addWidget(self.playback_slider)

        # 时间标签
        self.playback_time_label = QtWidgets.QLabel("00:00 / 00:00")
        layout.addWidget(self.playback_time_label)

        # 控制按钮
        btn_layout = QtWidgets.QHBoxLayout()

        btn_play = QtWidgets.QPushButton("▶ 播放")
        btn_play.clicked.connect(self.playback_ctrl.play)
        btn_layout.addWidget(btn_play)

        btn_pause = QtWidgets.QPushButton("⏸ 暂停")
        btn_pause.clicked.connect(self.playback_ctrl.pause)
        btn_layout.addWidget(btn_pause)

        btn_stop = QtWidgets.QPushButton("⏹ 停止")
        btn_stop.clicked.connect(self.playback_ctrl.stop)
        btn_layout.addWidget(btn_stop)

        btn_layout.addWidget(QtWidgets.QLabel("速度:"))
        speed_combo = QtWidgets.QComboBox()
        speed_combo.addItems(['0.5x', '1x', '2x', '4x'])
        speed_combo.setCurrentIndex(1)
        speed_combo.currentIndexChanged.connect(
            lambda idx: self.playback_ctrl.set_speed([0.5, 1.0, 2.0, 4.0][idx])
        )
        btn_layout.addWidget(speed_combo)

        layout.addLayout(btn_layout)

        # 连接信号
        self.playback_ctrl.progress_updated.connect(self.playback_slider.setValue)
        self.playback_ctrl.progress_updated.connect(
            lambda v: self.playback_time_label.setText(
                f"{self.playback_ctrl.duration * v / 100:.0f}s / {self.playback_ctrl.duration:.0f}s"
            )
        )
        self.playback_ctrl.playback_finished.connect(lambda: self.log_info('回放结束'))
        self.playback_ctrl.playback_finished.connect(panel.close)

        # 回放期间禁用记录/滤波/标记控件，防止误操作
        self.btn_open_com.setEnabled(False)
        self.btn_close_com.setEnabled(False)
        self.hp_check.setEnabled(False)
        self.hp_spin.setEnabled(False)
        self.lp_check.setEnabled(False)
        self.lp_spin.setEnabled(False)
        self.notch_combo.setEnabled(False)
        self.notch_bw_spin.setEnabled(False)
        self.marker_combo.setEnabled(False)
        self.marker_custom_edit.setEnabled(False)
        self.btn_insert_marker.setEnabled(False)

        def _on_panel_done():
            self.btn_open_com.setEnabled(True)
            self.btn_close_com.setEnabled(True)
            self.hp_check.setEnabled(True)
            self.hp_spin.setEnabled(self.hp_check.isChecked())
            self.lp_check.setEnabled(True)
            self.lp_spin.setEnabled(self.lp_check.isChecked())
            self.notch_combo.setEnabled(True)
            self.notch_bw_spin.setEnabled(self.notch_combo.currentIndex() != 0)
            self.marker_combo.setEnabled(True)
            self.marker_custom_edit.setEnabled(True)
            self.btn_insert_marker.setEnabled(True)

        panel.finished.connect(self.playback_ctrl.stop)
        panel.finished.connect(_on_panel_done)
        panel.show()
        self._playback_panel = panel

    def dev_evt(self, s):
        self.log_info(s)
