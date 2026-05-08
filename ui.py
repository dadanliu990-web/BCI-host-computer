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

        # 2. 元数据输入行
        meta_widget = QtWidgets.QWidget()
        meta_layout = QtWidgets.QHBoxLayout(meta_widget)
        meta_layout.setContentsMargins(0, 0, 0, 0)

        meta_layout.addWidget(QtWidgets.QLabel("被试ID:"))
        self.subject_edit = QtWidgets.QLineEdit()
        self.subject_edit.setPlaceholderText("如 S001")
        self.subject_edit.setFixedWidth(80)
        meta_layout.addWidget(self.subject_edit)

        meta_layout.addWidget(QtWidgets.QLabel("Session:"))
        self.session_edit = QtWidgets.QLineEdit()
        self.session_edit.setPlaceholderText("如 session1")
        self.session_edit.setFixedWidth(100)
        meta_layout.addWidget(self.session_edit)

        meta_layout.addWidget(QtWidgets.QLabel("备注:"))
        self.notes_edit = QtWidgets.QLineEdit()
        self.notes_edit.setPlaceholderText("可选备注")
        self.notes_edit.setFixedWidth(150)
        meta_layout.addWidget(self.notes_edit)

        meta_layout.addStretch()
        data_layout.addWidget(meta_widget)

        # 3. 按钮行
        button_widget = QtWidgets.QWidget()
        button_layout = QtWidgets.QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_open_com.setFixedWidth(150)
        self.btn_close_com.setFixedWidth(150)

        button_layout.addWidget(self.btn_open_com)
        button_layout.addStretch()
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
        self.marker_combo.setFixedWidth(120)
        marker_layout.addWidget(self.marker_combo)

        self.marker_custom_edit = QtWidgets.QLineEdit()
        self.marker_custom_edit.setPlaceholderText("自定义标签")
        self.marker_custom_edit.setFixedWidth(120)
        self.marker_custom_edit.setVisible(False)
        marker_layout.addWidget(self.marker_custom_edit)

        self.marker_combo.currentTextChanged.connect(lambda t: self.marker_custom_edit.setVisible(t == 'custom'))

        self.btn_insert_marker = QtWidgets.QPushButton("插入标记")
        self.btn_insert_marker.setFixedWidth(80)
        self.btn_insert_marker.clicked.connect(self._on_insert_marker)
        marker_layout.addWidget(self.btn_insert_marker)

        marker_layout.addSpacing(16)
        filter_label = QtWidgets.QLabel("滤波:")
        marker_layout.addWidget(filter_label)
        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.setFixedWidth(110)
        self.filter_combo.setToolTip("选择滤波器预设")
        marker_layout.addWidget(self.filter_combo)

        marker_layout.addStretch()
        self.marker_widget = marker_widget

        central_widget = self.centralWidget()
        layout = central_widget.layout()
        if layout:
            layout.insertWidget(0, data_group)
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

            # ==== Row 0: 事件标记 & 滤波 ====
            grid.addWidget(self.marker_widget, 0, 0, 1, 4)

            # ==== Row 1: 断开连接 | 重连 | 回放 ====
            self.btn_con_dev.setText("断开连接")
            self.btn_con_dev.setCheckable(True)
            self.btn_con_dev.setChecked(False)
            self.btn_con_dev.setMinimumWidth(80)
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

            self.btn_reconnect.setMinimumWidth(90)
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

            # ==== Row 2: 阻抗检测 | 频带能量 | 时频图 | 加速度计 ====
            self.btn_impedance = QtWidgets.QPushButton("阻抗检测")
            self.btn_impedance.setCheckable(True)
            self.btn_impedance.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    min-width: 90px;
                    min-height: 36px;
                    padding-left: 10px;
                    padding-right: 10px;
                    background-color: #444;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #9C27B0;
                    color: white;
                }
            """)
            self.btn_impedance.toggled.connect(self._on_impedance_check)
            grid.addWidget(self.btn_impedance, 2, 0)

            self.btn_bandpower = QtWidgets.QPushButton("频带能量")
            self.btn_bandpower.setCheckable(True)
            self.btn_bandpower.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    min-width: 90px;
                    min-height: 36px;
                    padding-left: 10px;
                    padding-right: 10px;
                    background-color: #444;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #1565C0;
                    color: white;
                }
            """)
            self.btn_bandpower.toggled.connect(self._on_bandpower_toggled)
            grid.addWidget(self.btn_bandpower, 2, 1)

            self.btn_spectrogram = QtWidgets.QPushButton("时频图")
            self.btn_spectrogram.setCheckable(True)
            self.btn_spectrogram.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    min-width: 90px;
                    min-height: 36px;
                    padding-left: 10px;
                    padding-right: 10px;
                    background-color: #444;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #00838F;
                    color: white;
                }
            """)
            self.btn_spectrogram.toggled.connect(self._on_spectrogram_toggled)
            grid.addWidget(self.btn_spectrogram, 2, 2)

            self.btn_accelerometer = QtWidgets.QPushButton("加速度计")
            self.btn_accelerometer.setCheckable(True)
            self.btn_accelerometer.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    min-width: 90px;
                    min-height: 36px;
                    padding-left: 10px;
                    padding-right: 10px;
                    background-color: #444;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #C62828;
                    color: white;
                }
            """)
            self.btn_accelerometer.toggled.connect(self._on_accelerometer_toggled)
            grid.addWidget(self.btn_accelerometer, 2, 3)

            self.btn_topomap = QtWidgets.QPushButton("头皮拓扑图")
            self.btn_topomap.setCheckable(True)
            self.btn_topomap.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 16px;
                    min-width: 90px;
                    min-height: 36px;
                    padding-left: 10px;
                    padding-right: 10px;
                    background-color: #444;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #F57C00;
                    color: white;
                }
            """)
            self.btn_topomap.toggled.connect(self._on_topomap_toggled)
            grid.addWidget(self.btn_topomap, 1, 3)

            grid.setColumnStretch(4, 1)

            self.groupBox_connect.setTitle("控制面板")

            old_layout.addWidget(container)


        # 隐藏未使用的 BCI 实训 GroupBox（释放垂直空间）
        self.groupBox_cursor.show()
        self.groupBox_motor.show()
        self.groupBox_eye.show()

        # 初始化滤波预设下拉
        self._init_filter_presets()

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

    def _on_impedance_check(self, checked: bool):
        """打开/关闭阻抗/信号质量检测窗口"""
        if self.controller is None:
            self.log_info('Controller 未就绪')
            return
        if checked:
            if self.controller.impf is not None:
                self.controller.impf.show()
                self.controller.impf.raise_()
            self.controller.start_impedance_check()
        else:
            self.controller.stop_impedance_check()
            if self.controller.impf is not None:
                self.controller.impf.hide()

    def _on_bandpower_toggled(self, checked: bool):
        if hasattr(self, 'bpf') and self.bpf is not None:
            if checked:
                self.bpf.show()
                self.bpf.raise_()
            else:
                self.bpf.hide()

    def _on_spectrogram_toggled(self, checked: bool):
        if hasattr(self, 'sgf') and self.sgf is not None:
            if checked:
                self.sgf.show()
                self.sgf.raise_()
            else:
                self.sgf.hide()

    def _on_accelerometer_toggled(self, checked: bool):
        if hasattr(self, 'af') and self.af is not None:
            if checked:
                self.af.show()
                self.af.raise_()
            else:
                self.af.hide()

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

    def _init_filter_presets(self):
        """初始化滤波预设下拉列表"""
        import json
        try:
            preset_file = os.path.join(os.path.dirname(__file__), "ui_config", "filter_presets.json")
            if os.path.exists(preset_file):
                with open(preset_file, 'r') as f:
                    data = json.load(f)
                    presets = data.get('presets', {})
                    self.filter_combo.addItems(list(presets.keys()))
            else:
                self.filter_combo.addItem('RAW')
        except Exception as e:
            self.log_info(f'滤波器预设加载失败: {e}')
            self.filter_combo.addItem('RAW')
        self.filter_combo.currentTextChanged.connect(self._on_filter_preset_changed)

    def _on_filter_preset_changed(self, preset_name):
        """切换滤波预设"""
        if self.controller is None:
            return
        if hasattr(self.controller, 'dsp') and self.controller.dsp is not None:
            success = self.controller.dsp.load_preset(preset_name)
            if success:
                self.log_info(f'滤波预设已切换: {preset_name}')
            else:
                self.log_info(f'切换滤波预设失败: {preset_name}')

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
        self.filter_combo.setEnabled(False)
        self.marker_combo.setEnabled(False)
        self.marker_custom_edit.setEnabled(False)
        self.btn_insert_marker.setEnabled(False)

        def _on_panel_done():
            self.btn_open_com.setEnabled(True)
            self.btn_close_com.setEnabled(True)
            self.filter_combo.setEnabled(True)
            self.marker_combo.setEnabled(True)
            self.marker_custom_edit.setEnabled(True)
            self.btn_insert_marker.setEnabled(True)

        panel.finished.connect(self.playback_ctrl.stop)
        panel.finished.connect(_on_panel_done)
        panel.show()
        self._playback_panel = panel

    def dev_evt(self, s):
        self.log_info(s)