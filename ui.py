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
from PyQt5.QtWidgets import QInputDialog, QLineEdit, QDoubleSpinBox
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

        # 所有行统一布局在下方 groupBox_connect 重组区，保证等宽对齐
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

        # ========== 统一布局：所有行等宽对齐，控件随窗口横向拉伸 ==========
        parent = self.btn_reconnect.parent()
        if parent and parent.layout():
            old_layout = parent.layout()
            while old_layout.count():
                old_layout.takeAt(0)

            EXPAND = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            M = (0, 0, 0, 0)

            container = QtWidgets.QWidget()
            root = QtWidgets.QVBoxLayout(container)
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(6)

            # ── 数据记录 ──
            sec1 = QtWidgets.QLabel("数据记录")
            sec1.setStyleSheet("font-weight: bold; color: #37474F; padding-top: 2px;")
            root.addWidget(sec1)

            # Row 0: 保存路径
            pw = QtWidgets.QWidget(); pl = QtWidgets.QHBoxLayout(pw); pl.setContentsMargins(*M)
            pl.addWidget(QtWidgets.QLabel("保存路径:"))
            self.path_line_edit = QtWidgets.QLineEdit()
            self.path_line_edit.setReadOnly(True); self.path_line_edit.setText("./data")
            self.path_line_edit.setPlaceholderText("请选择保存目录")
            self.path_line_edit.setSizePolicy(EXPAND)
            browse_btn = QtWidgets.QPushButton("\U0001f4c1"); browse_btn.setFixedSize(35, 28)
            browse_btn.setToolTip("选择保存路径"); browse_btn.clicked.connect(self.browse_save_path)
            pl.addWidget(self.path_line_edit); pl.addWidget(browse_btn)
            root.addWidget(pw)

            # Row 1: 被试ID / Session / 备注
            mw = QtWidgets.QWidget(); ml = QtWidgets.QHBoxLayout(mw); ml.setContentsMargins(*M)
            ml.addWidget(QtWidgets.QLabel("被试ID:"))
            self.subject_edit = QtWidgets.QLineEdit()
            self.subject_edit.setPlaceholderText("如 S001"); self.subject_edit.setMaximumWidth(100)
            self.subject_edit.setSizePolicy(EXPAND); ml.addWidget(self.subject_edit)
            ml.addWidget(QtWidgets.QLabel("Session:"))
            self.session_edit = QtWidgets.QLineEdit()
            self.session_edit.setPlaceholderText("如 session1"); self.session_edit.setMaximumWidth(120)
            self.session_edit.setSizePolicy(EXPAND); ml.addWidget(self.session_edit)
            ml.addWidget(QtWidgets.QLabel("备注:"))
            self.notes_edit = QtWidgets.QLineEdit()
            self.notes_edit.setPlaceholderText("可选备注")
            self.notes_edit.setSizePolicy(EXPAND); ml.addWidget(self.notes_edit)
            root.addWidget(mw)

            # Row 2: 开始记录 / 停止记录
            bw = QtWidgets.QWidget(); bl = QtWidgets.QHBoxLayout(bw); bl.setContentsMargins(*M)
            self.btn_open_com.setFixedWidth(150); self.btn_close_com.setFixedWidth(150)
            bl.addWidget(self.btn_open_com); bl.addStretch(); bl.addWidget(self.btn_close_com)
            root.addWidget(bw)

            # ── 控制面板 ──
            sec2 = QtWidgets.QLabel("控制面板")
            sec2.setStyleSheet("font-weight: bold; color: #37474F; padding-top: 4px;")
            root.addWidget(sec2)

            # Row 3: 事件标记
            mkw = QtWidgets.QWidget(); mkl = QtWidgets.QHBoxLayout(mkw); mkl.setContentsMargins(*M)
            mkl.addWidget(QtWidgets.QLabel("事件标记:"))
            self.marker_combo = QtWidgets.QComboBox()
            self.marker_combo.addItems(['artifact', 'movement', 'blink', 'instruction',
                                        'rest_start', 'rest_end', 'custom'])
            self.marker_combo.setSizePolicy(EXPAND); mkl.addWidget(self.marker_combo, 3)
            self.marker_custom_edit = QtWidgets.QLineEdit()
            self.marker_custom_edit.setPlaceholderText("自定义标签")
            self.marker_custom_edit.setSizePolicy(EXPAND); self.marker_custom_edit.setVisible(False)
            mkl.addWidget(self.marker_custom_edit, 2)
            self.marker_combo.currentTextChanged.connect(
                lambda t: self.marker_custom_edit.setVisible(t == 'custom'))
            self.btn_insert_marker = QtWidgets.QPushButton("插入标记")
            self.btn_insert_marker.setMinimumWidth(80)
            self.btn_insert_marker.setSizePolicy(EXPAND); mkl.addWidget(self.btn_insert_marker, 1)
            self.btn_insert_marker.clicked.connect(self._on_insert_marker)
            root.addWidget(mkw)

            # Row 4: 断开连接 / 重连 / 回放
            cw = QtWidgets.QWidget(); cl = QtWidgets.QHBoxLayout(cw); cl.setContentsMargins(*M)
            self.btn_con_dev.setText("断开连接")
            self.btn_con_dev.setCheckable(True); self.btn_con_dev.setChecked(False)
            self.btn_con_dev.setMinimumWidth(100); self.btn_con_dev.setSizePolicy(EXPAND)
            self.btn_con_dev.setStyleSheet("QPushButton { border:none; border-radius:14px; min-width:100px; min-height:30px; padding:4px 8px; background-color:#546E7A; color:white; font-weight:bold; } QPushButton:checked { background-color:#C62828; color:white; }")
            self.btn_con_dev.toggled.connect(self._on_disconnect)
            self.btn_reconnect.setMinimumWidth(100); self.btn_reconnect.setSizePolicy(EXPAND)
            self.btn_reconnect.setStyleSheet("QPushButton { border:none; border-radius:14px; min-width:100px; min-height:30px; padding:4px 8px; background-color:#546E7A; color:white; font-weight:bold; }")
            self.btn_playback = QtWidgets.QPushButton("回放")
            self.btn_playback.setMinimumWidth(100); self.btn_playback.setSizePolicy(EXPAND)
            self.btn_playback.setStyleSheet("QPushButton { border:none; border-radius:16px; min-width:100px; min-height:36px; padding:4px 8px; background-color:#00796B; color:white; font-weight:bold; }")
            self.btn_playback.clicked.connect(self._on_playback)
            cl.addWidget(self.btn_con_dev, 1); cl.addWidget(self.btn_reconnect, 1)
            cl.addWidget(self.btn_playback, 1)
            root.addWidget(cw)

            # Row 5: 高通 / 低通 / 陷波
            fw = QtWidgets.QWidget(); fl = QtWidgets.QHBoxLayout(fw); fl.setContentsMargins(*M)
            fl.addWidget(QtWidgets.QLabel("高通:"))
            self.highpass_spin = QDoubleSpinBox()
            self.highpass_spin.setToolTip("高通截止频率 (Hz)")
            self.highpass_spin.setRange(0.0, 30.0); self.highpass_spin.setSingleStep(0.1)
            self.highpass_spin.setDecimals(1); self.highpass_spin.setSpecialValueText("Off")
            self.highpass_spin.setValue(0.0); self.highpass_spin.setSuffix(" Hz")
            self.highpass_spin.setSizePolicy(EXPAND)
            self.highpass_spin.valueChanged.connect(self._on_highpass_changed)
            fl.addWidget(self.highpass_spin, 1)
            fl.addWidget(QtWidgets.QLabel("低通:"))
            self.lowpass_spin = QDoubleSpinBox()
            self.lowpass_spin.setToolTip("低通截止频率 (Hz)")
            self.lowpass_spin.setRange(0.0, 120.0); self.lowpass_spin.setSingleStep(1.0)
            self.lowpass_spin.setDecimals(0); self.lowpass_spin.setSpecialValueText("Off")
            self.lowpass_spin.setValue(0.0); self.lowpass_spin.setSuffix(" Hz")
            self.lowpass_spin.setSizePolicy(EXPAND)
            self.lowpass_spin.valueChanged.connect(self._on_lowpass_changed)
            fl.addWidget(self.lowpass_spin, 1)
            fl.addWidget(QtWidgets.QLabel("陷波:"))
            self.notch_combo = QtWidgets.QComboBox()
            self.notch_combo.setToolTip("陷波滤波去除工频干扰")
            self.notch_combo.addItems(['Off', '50', '60']); self.notch_combo.setCurrentIndex(0)
            self.notch_combo.setSizePolicy(EXPAND)
            self.notch_combo.currentTextChanged.connect(self._on_notch_changed)
            fl.addWidget(self.notch_combo, 1)
            root.addWidget(fw)

            self.groupBox_connect.setTitle("")
            old_layout.addWidget(container)


        # 隐藏未使用的 BCI 实训 GroupBox（释放垂直空间）
        self.groupBox_cursor.show()
        self.groupBox_motor.show()
        self.groupBox_eye.show()

        # 初始化滤波预设下拉
        self.btn_mi_train.clicked.connect(self.mi_train_btn_click)
        self.btn_mi_test.clicked.connect(self.mi_test_btn_click)
        self.btn_generate_model.clicked.connect(self.btn_generate_model_btn_click)
        self.btn_curctrl_train.clicked.connect(self.curctrl_train_btn_click)
        self.btn_curctrl_task.clicked.connect(self.curctrl_task_btn_click)
        self.btn_generate_curctrl_model.clicked.connect(self.btn_generate_curctrl_model_btn_click)

        self.btn_eye_open_close.clicked.connect(self.eye_open_close_btn_click)
        self.btn_alpha_calibration.clicked.connect(self.alpha_calibration_btn_click)

        self.btn_alpha_detection.setCheckable(True)
        self.btn_alpha_detection.setText("OFF")
        self.btn_alpha_detection.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 22px;
                min-width: 110px;
                min-height: 44px;
                padding-left: 12px;
                padding-right: 12px;
                background-color: #444;
                color: white;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #00C853;
                color: white;
            }
            """)

        self.btn_alpha_detection.toggled.connect(self.on_alpha_switch)

        self.c = None

        self.settings = QSettings('./uiSetting.ini', QSettings.IniFormat)
        self.settings.remove("size")
        self.settings.remove("pos")
        self.resize(520, 680)
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

    # === 已注销: 阻抗检测功能 ===
    # def _on_impedance_check(self, checked: bool):
    #     """打开/关闭阻抗/信号质量检测窗口"""
    #     if self.controller is None:
    #         self.log_info('Controller 未就绪')
    #         return
    #     if checked:
    #         if self.controller.impf is not None:
    #             self.controller.impf.show()
    #             self.controller.impf.raise_()
    #         self.controller.start_impedance_check()
    #     else:
    #         self.controller.stop_impedance_check()
    #         if self.controller.impf is not None:
    #             self.controller.impf.hide()

    # === 已注销: 频带能量功能 ===
    # def _on_bandpower_toggled(self, checked: bool):
    #     if hasattr(self, 'bpf') and self.bpf is not None:
    #         if checked:
    #             self.bpf.show()
    #             self.bpf.raise_()
    #         else:
    #             self.bpf.hide()

    # === 已注销: 时频图功能 ===
    # def _on_spectrogram_toggled(self, checked: bool):
    #     if hasattr(self, 'sgf') and self.sgf is not None:
    #         if checked:
    #             self.sgf.show()
    #             self.sgf.raise_()
    #         else:
    #             self.sgf.hide()

    # === 已注销: 加速度计功能 ===
    # def _on_accelerometer_toggled(self, checked: bool):
    #     if hasattr(self, 'af') and self.af is not None:
    #         if checked:
    #             self.af.show()
    #             self.af.raise_()
    #         else:
    #             self.af.hide()

    def _on_topomap_toggled(self, checked: bool):
        if hasattr(self, 'topo') and self.topo is not None:
            if checked:
                self.topo.show()
                self.topo.raise_()
            else:
                self.topo.hide()

    def flash_led_triggered(self):
        dp.dpt('flash_led_triggered - - -')
        self.evt_win.emit(cv.SERIAL_CMD_FALSH_LED, cv.DUMMY_STR)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Q:
            self.close()

    def curctrl_task_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_CURCTRL, cv.DUMMY_STR)

    def curctrl_train_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_CURCTRL_TRAIN, cv.DUMMY_STR)

    def mi_train_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_MI_TRAIN, cv.DUMMY_STR)

    def mi_test_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_MI_TEST, cv.DUMMY_STR)

    def eye_open_close_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_EYE_OC, cv.DUMMY_STR)

    def alpha_calibration_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_BTN_ALPHA_CALIBRATION, cv.DUMMY_STR)

    def on_alpha_switch(self, on: bool):
        self.btn_alpha_detection.setText("ON" if on else "OFF")
        self.evt_win.emit(cv.EVT_WIN_BTN_ALPHA_DETECTION, cv.DUMMY_STR)

    def btn_generate_model_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_GENERATW_MODEL, cv.DUMMY_STR)

    def btn_generate_curctrl_model_btn_click(self):
        self.evt_win.emit(cv.EVT_WIN_GENERATW_CURCTRL_MODEL, cv.DUMMY_STR)

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
            if self.impf is not None:
                self.impf.close()
                self.impf = None
            if self.bpf is not None:
                self.bpf.close()
                self.bpf = None
            if self.sgf is not None:
                self.sgf.close()
                self.sgf = None
            if self.af is not None:
                self.af.close()
                self.af = None
            if self.topo is not None:
                self.topo.close()
                self.topo = None

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

    def _on_highpass_changed(self, value):
        """高通截止频率变更，0.0 表示关闭"""
        if self.controller is None:
            return
        freq = None if value == 0.0 else value
        self.controller.set_highpass(freq)

    def _on_lowpass_changed(self, value):
        """低通截止频率变更，0.0 表示关闭"""
        if self.controller is None:
            return
        freq = None if value == 0.0 else value
        self.controller.set_lowpass(freq)

    def _on_notch_changed(self, text):
        """陷波频率变更"""
        if self.controller is None:
            return
        freq = None if text == 'Off' else float(text)
        self.controller.set_notch(freq)

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
            cf=self.cf, sf=self.sf, impf=getattr(self, 'impf', None),
            bpf=getattr(self, 'bpf', None),
            sgf=getattr(self, 'sgf', None),
            af=getattr(self, 'af', None),
            topo=getattr(self, 'topo', None),
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
        self.highpass_spin.setEnabled(False)
        self.lowpass_spin.setEnabled(False)
        self.notch_combo.setEnabled(False)
        self.marker_combo.setEnabled(False)
        self.marker_custom_edit.setEnabled(False)
        self.btn_insert_marker.setEnabled(False)

        def _on_panel_done():
            self.btn_open_com.setEnabled(True)
            self.btn_close_com.setEnabled(True)
            self.highpass_spin.setEnabled(True)
            self.lowpass_spin.setEnabled(True)
            self.notch_combo.setEnabled(True)
            self.marker_combo.setEnabled(True)
            self.marker_custom_edit.setEnabled(True)
            self.btn_insert_marker.setEnabled(True)

        panel.finished.connect(self.playback_ctrl.stop)
        panel.finished.connect(_on_panel_done)
        panel.show()
        self._playback_panel = panel

    def dev_evt(self, s):
        self.log_info(s)