import struct
from datetime import datetime
from time import sleep

from PySide6.QtWidgets import (
    QMainWindow, QSystemTrayIcon, QMenu, QPushButton, QMessageBox,
    QLabel, QTextEdit, QApplication
)
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QFont, QFontMetrics
from PySide6.QtCore import Qt, QTimer, QFile, QThread
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QFrame

# --- 本地模块导入 ---
from serial_worker import SerialWorker
from config_handler import ConfigHandler
from database_handler import DatabaseHandler
from history_window import HistoryWindow
import constants as const
from mouse_handler import MouseDataProcessor
from utils import resource_path 


LOGGING_ENABLED = True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. 运行时加载 UI
        self._load_ui(resource_path("main.ui")) # <--- 使用新函数
        self.setFixedSize(self.size())          # 禁止调整窗口大小
        self._center_window()                   # 窗口居中
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
        self.setWindowFlags(Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)

        # --- 图标 ---
        self.icon_heart = self._create_emoji_icon('❤️')
        self.icon_white_heart = self._create_emoji_icon('🩶')
        self.is_heart_icon = False
        self.setWindowIcon(self.icon_heart)
        
        # --- 绑定 UI 控件 ---
        self.start_button = self.findChild(QPushButton, "btn_start")
        if self.start_button:
            self.start_button.clicked.connect(self.on_start_button_clicked)
            
        # --- 绑定历史数据按钮 ---
        self.history_button = self.findChild(QPushButton, "btn_history")
        if self.history_button:
            self.history_button.clicked.connect(self.show_history_window)
        else:
            print("警告: 未在 UI 文件中找到名为 'btn_history' 的 QPushButton。")
        
        # --- 绑定刷新鼠标数据按钮 ---
        self.mousedata_button = self.findChild(QPushButton, "btn_mousedata")
        if self.mousedata_button:
            self.mousedata_button.clicked.connect(self.on_mousedata_button_clicked)
        else:
            print("警告: 未在 UI 文件中找到名为 'btn_mousedata' 的 QPushButton。")
            
        self.metric_keys = [
            'heartrate', 'spo2', 'bk', 'fatigue', 'systolic', 'diastolic', 
            'cardiac', 'resistance', 'rr_interval', 'sdnn', 'rmssd', 
            'nn50', 'pnn50', 'timestamp'
        ]
        
        ui_label_names = {
            'heartrate': 'label_hr_value', 'spo2': 'label_spo2_value',
            'bk': 'label_mc_value', 'fatigue': 'label_fi_value',
            'systolic': 'label_sbp_value', 'diastolic': 'label_dbp_value',
            'cardiac': 'label_co_value', 'resistance': 'label_pr_value'
        }

        self.value_labels = {}
        for key, name in ui_label_names.items():
            label = self.findChild(QLabel, name)
            if label:
                self.value_labels[key] = label
                if key in const.HEALTH_METRICS_TOOLTIPS:
                    label.setToolTip(const.HEALTH_METRICS_TOOLTIPS[key])
            else:
                print(f"警告: 未在 UI 文件中找到名为 '{name}' 的 QLabel。")

        # 鼠标统计值标签
        self.label_distance = self.findChild(QLabel, "label_distance")
        self.label_leftclick = self.findChild(QLabel, "label_leftclick")
        self.label_midclick = self.findChild(QLabel, "label_midclick")
        self.label_rightclick = self.findChild(QLabel, "label_rightclick")

        self.log_output = self.findChild(QTextEdit, "log_output")
        if self.log_output:
            self.log_output.setReadOnly(True)

        # --- 系统托盘 ---
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.icon_heart)
        tray_menu = QMenu()
        show_action = QAction("显示主界面", self)
        about_action = QAction("关于", self)
        exit_action = QAction("退出", self)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(about_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._handle_tray_activation)
        show_action.triggered.connect(self.show_window)
        about_action.triggered.connect(self._show_about_dialog)
        exit_action.triggered.connect(self.exit_app)
        self.tray_icon.show()

        # --- 定时器 ---
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(500)
        self.blink_timer.timeout.connect(self._toggle_icon)
        
        self.detection_timeout_timer = QTimer(self)
        self.detection_timeout_timer.setSingleShot(True)
        self.detection_timeout_timer.setInterval(100 * 1000)  # 延长超时到100秒
        self.detection_timeout_timer.timeout.connect(self.on_detection_timeout)
        
        # 开始体检倒计时（ACK 后启动）
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._on_countdown_tick)
        self.countdown_remaining = 0
        
        # --- 状态栏 ---
        self._init_status_bar()

        # --- 业务逻辑处理器 ---
        self.config_handler = ConfigHandler()
        self.db_handler = DatabaseHandler(metric_keys=self.metric_keys)
        self._init_serial()

        self.startup_data_loaded = False
        self.history_window_instance = None # 用于持有历史窗口的实例
        self.startup_sequence()
        
        # 鼠标数据处理器
        self.mouse_processor = MouseDataProcessor(self.db_handler)

    def _init_serial(self):
        """初始化串口工作线程"""
        self.serial_thread = QThread()
        self.serial_worker = SerialWorker()
        self.serial_worker.moveToThread(self.serial_thread)

        self.serial_worker.error_occurred.connect(self._show_error)
        self.serial_worker.log_message.connect(self._log_to_ui)
        self.serial_worker.ack_received.connect(self.on_ack_received)
        self.serial_worker.health_data_received.connect(self.on_health_data_received)
        self.serial_worker.mouse_data_received.connect(self.on_mouse_data_received)
        self.serial_worker.connected.connect(self._update_status_connected)
        self.serial_worker.disconnected.connect(self._update_status_disconnected)

        self.serial_thread.started.connect(self.serial_worker.run)
        # self.serial_worker.disconnected.connect(self.serial_thread.quit) # 在自动重连模式下，线程不应轻易退出
        
    def startup_sequence(self):
        """应用启动时的操作序列"""
        self._log_to_ui("应用启动... 优先从设备获取最新数据。")
        self.startup_data_loaded = False
        self.startup_mouse_loaded = False
        
        try:
            com_port = self.config_handler.get_com_port()
            self.serial_worker.connect_serial(com_port)
            
            if self.serial_worker.is_running and not self.serial_thread.isRunning():
                self.serial_thread.start()

            
            QTimer.singleShot(100, lambda: self.serial_worker.send_frame(const.CMD_GET_LAST_HEALTH_DATA))
            QTimer.singleShot(120, lambda: self.serial_worker.send_frame(const.CMD_GET_MOUSE_DATA))
            QTimer.singleShot(5000, self.check_startup_data)

        except Exception as e:
            self._log_to_ui(f"启动时连接串口失败: {e}。尝试从本地文件加载...")
            self._load_history_from_db()
            self._load_mouse_from_db()

    def check_startup_data(self):
        """在启动超时后检查数据是否已加载"""
        if not self.startup_data_loaded:
            self._log_to_ui("从设备获取数据超时，尝试从本地文件加载...")
            self._load_history_from_db()
        if not self.startup_mouse_loaded:
            self._log_to_ui("从设备获取鼠标数据超时，尝试从数据库加载...")
            self._load_mouse_from_db()

    def _load_history_from_db(self):
        """从数据库读取并显示最后一条历史数据"""
        last_record = self.db_handler.load_last_record()
        if last_record:
            timestamp = last_record.pop('created_at')
            self._log_to_ui(f"从数据库加载历史数据 ({timestamp}): {last_record}")
            self._update_data_labels(last_record)
            self.startup_data_loaded = True
        else:
            self._log_to_ui("数据库中无历史数据。")

    def _load_mouse_from_db(self):
        """从数据库读取并显示鼠标累计数据"""
        mouse = self.db_handler.load_mouse_data()
        if mouse:
            # 使用处理器进行单位转换输出
            distance_m = None
            try:
                distance_m = self.mouse_processor.pixels_to_meters_str(mouse['distance'])
            except Exception:
                distance_m = None
            if distance_m:
                self._log_to_ui(
                    f"从数据库加载鼠标数据 ({mouse['created_at']}): 距离={mouse['distance']}px (~{distance_m}), "
                    f"L={mouse['left_click']}, M={mouse['mid_click']}, R={mouse['right_click']}"
                )
            else:
                self._log_to_ui(
                    f"从数据库加载鼠标数据 ({mouse['created_at']}): 距离={mouse['distance']}px, "
                    f"L={mouse['left_click']}, M={mouse['mid_click']}, R={mouse['right_click']}"
                )
            self._update_mouse_labels(mouse['distance'], mouse['left_click'], mouse['mid_click'], mouse['right_click'])
            self.startup_mouse_loaded = True
        else:
            self._log_to_ui("数据库中无鼠标数据。")

    def on_start_button_clicked(self):
        """处理开始按钮点击事件"""
        self._log_to_ui("点击了开始按钮...")
        self._start_blinking()
        self.detection_timeout_timer.start()
        if self.start_button:
            self.start_button.setEnabled(False)
            self.start_button.setText("体检中...")
        try:
            com_port = self.config_handler.get_com_port()
            if not self.serial_worker.serial_port or not self.serial_worker.serial_port.is_open:
                self.serial_worker.connect_serial(com_port)
                if self.serial_worker.is_running and not self.serial_thread.isRunning():
                    self.serial_thread.start()
                QTimer.singleShot(100, lambda: self.serial_worker.send_frame(const.CMD_START_HEALTH_CHECK))
            else:
                self.serial_worker.send_frame(const.CMD_START_HEALTH_CHECK)
        except Exception as e:
            self._show_error(f"开始体检失败: {e}")
            if self.start_button:
                self.start_button.setEnabled(True)
                self.start_button.setText("开始体检")

    def on_mousedata_button_clicked(self):
        """处理刷新鼠标数据按钮点击事件"""
        self._log_to_ui("刷新鼠标数据...")
        try:
            com_port = self.config_handler.get_com_port()
            if not self.serial_worker.serial_port or not self.serial_worker.serial_port.is_open:
                self.serial_worker.connect_serial(com_port)
                if self.serial_worker.is_running and not self.serial_thread.isRunning():
                    self.serial_thread.start()
            self.serial_worker.send_frame(const.CMD_GET_MOUSE_DATA)
        except Exception as e:
            self._show_error(f"刷新鼠标数据失败: {e}")

    def _show_error(self, message: str):
        # QMessageBox.critical(self, "错误", message) # 禁用弹窗
        self._log_to_ui(f"错误: {message}")
        # 发生任何严重错误时，都应尝试重置状态
        self._reset_detection_state()

    def _show_about_dialog(self):
        """显示关于对话框"""
        QMessageBox.about(self, 
            "关于", 
            "<p style='font-size: 1px;'>&nbsp;</p>"
            "<p style='font-size: 14px; font-weight: bold;'> CyMouse 数据查看工具 v1.0 &nbsp;</p>"
            "<p align='center'>Powered by <a href='https://cynix.cc' style='color: #89b4fa;'>Cynix.cc</a>&nbsp;&nbsp;&nbsp;</p>"
        )

    def _log_to_ui(self, message: str):
        if not LOGGING_ENABLED:
            return
            
        if self.log_output:
            self.log_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        else:
            print(message)

    def on_ack_received(self, original_cmd: int, status_code: int):
        self._log_to_ui(f"收到 ACK: 原始命令={hex(original_cmd)}, 状态码={status_code}")
        if original_cmd == const.CMD_START_HEALTH_CHECK:
            if status_code == const.ACK_SUCCESS:
                self._log_to_ui("设备已确认开始健康监测。等待数据...")
                # 启动 90 秒倒计时
                self.countdown_remaining = 90
                if self.start_button:
                    self.start_button.setEnabled(False)
                    self.start_button.setText(f"{self.countdown_remaining}秒")
                if not self.countdown_timer.isActive():
                    self.countdown_timer.start()
            elif status_code == const.ACK_DEVICE_BUSY:
                self._log_to_ui("设备正忙，请稍后再试。")
                self._reset_detection_state()
            elif status_code == const.ACK_UNKNOWN_CMD:
                self._log_to_ui("设备无法识别开始命令，请检查固件版本。")
                self._reset_detection_state()
            else:
                self._log_to_ui(f"设备返回未知状态码 {status_code}，操作失败。")
                self._reset_detection_state()

    def on_detection_timeout(self):
        self._log_to_ui("错误: 健康监测超时 (90秒)，请重试。")
        self._reset_detection_state()

    def show_history_window(self):
        """显示历史数据窗口"""
        # 检查实例是否存在或已不可见，防止创建多个窗口
        if self.history_window_instance is None or not self.history_window_instance.isVisible():
            # 将 db_handler 中的 db_file 路径传递给历史窗口
            self.history_window_instance = HistoryWindow(
                db_path=self.db_handler.db_file, 
                parent=self
            )
        self.history_window_instance.show()
        self.history_window_instance.activateWindow() # 激活窗口到前台

    def on_health_data_received(self, data: bytes):
        if self.detection_timeout_timer.isActive():
            self.detection_timeout_timer.stop()

        self.startup_data_loaded = True
        self._stop_blinking()
        self._stop_countdown()
        self._log_to_ui(f"收到健康数据: {data.hex(' ').upper()}")
            
        if len(data) >= 16:
            try:
                format_string = '<BBBBBBBBBBBBBI'
                unpacked_data = struct.unpack(format_string, data)
                
                health_metrics = dict(zip(self.metric_keys, unpacked_data))
                print(health_metrics)

                self._update_data_labels(health_metrics)
                self.db_handler.save_record_if_new(list(unpacked_data))
                
                # 体检成功，重置状态
                self._reset_detection_state()

            except struct.error as e:
                self._log_to_ui(f"解析健康数据失败: {e}")
        else:
            self._log_to_ui(f"警告: 健康数据 payload 长度不正确 (收到 {len(data)} bytes)。")

    def _on_countdown_tick(self):
        if self.countdown_remaining > 0:
            self.countdown_remaining -= 1
        
        if self.start_button:
            if self.countdown_remaining > 0:
                self.start_button.setText(f"{self.countdown_remaining}秒")
            else:
                self.start_button.setText("处理中...")

        if self.countdown_remaining <= 0 and self.countdown_timer.isActive():
            self.countdown_timer.stop()

    def _stop_countdown(self):
        if self.countdown_timer.isActive():
            self.countdown_timer.stop()
        self.countdown_remaining = 0

    def on_mouse_data_received(self, payload: bytes):
        """处理收到的鼠标累计数据，更新界面并写入数据库。"""
        try:
            result = self.mouse_processor.process_payload(payload)
            self._log_to_ui(
                f"收到鼠标数据: 距离={result['distance_px']}px (~{result['distance_m_str']}), "
                f"L={result['left_click']}, M={result['mid_click']}, R={result['right_click']}"
            )
            self._update_mouse_labels(
                result['distance_px'],
                result['left_click'],
                result['mid_click'],
                result['right_click']
            )
            self.startup_mouse_loaded = True
        except Exception as e:
            self._log_to_ui(f"解析/处理鼠标数据失败: {e}")

    def _update_data_labels(self, data_dict: dict):
        for key, value in data_dict.items():
            if key in self.value_labels:
                display_value = value
                if key == 'cardiac':
                    # 将心输出值除以10，并格式化为一位小数的浮点数
                    try:
                        numeric_value = float(value)
                        display_value = f"{numeric_value / 10.0:.1f}"
                    except (ValueError, TypeError):
                        # 如果转换失败，则按原样显示
                        display_value = str(value)

                self.value_labels[key].setText(str(display_value))
        self._log_to_ui(f"界面数据已更新。")

    def _update_mouse_labels(self, distance: int, left: int, mid: int, right: int):
        if self.label_distance:
            # 使用米制字符串展示；若处理器不可用则兜底为像素值
            try:
                meters_text = None
                if hasattr(self, 'mouse_processor') and self.mouse_processor:
                    meters_text = self.mouse_processor.pixels_to_meters_str(distance)
                self.label_distance.setText(meters_text if meters_text else str(distance))
            except Exception:
                self.label_distance.setText(str(distance))
            
        if self.label_leftclick:
            self.label_leftclick.setText(str(left))
        if self.label_midclick:
            self.label_midclick.setText(str(mid))
        if self.label_rightclick:
            self.label_rightclick.setText(str(right))
        self._log_to_ui("鼠标数据已更新到界面。")

    def _center_window(self):
        """将窗口移动到屏幕中心"""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            # 手动计算居中位置，避免依赖未显示的 frameGeometry
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)

    def _load_ui(self, ui_path: str) -> None:
        loader = QUiLoader()
        ui_file = QFile(ui_path)
        if not ui_file.exists():
            raise FileNotFoundError(f"UI 文件未找到: {ui_path}")
        if not ui_file.open(QFile.ReadOnly):
            raise IOError(f"无法打开 UI 文件: {ui_path}")
        loaded = loader.load(ui_file)
        ui_file.close()
        if loaded is None:
            raise RuntimeError(f"加载 UI 失败: {ui_path}")

        # --- 提取样式表并应用到全局，以便子窗口（如历史窗口）也能继承样式 ---
        app_style = loaded.styleSheet()
        if app_style:
            QApplication.instance().setStyleSheet(app_style)
            loaded.setStyleSheet("") # 清除控件自身的样式表，避免双重应用

        if isinstance(loaded, QMainWindow):
            copied_title = loaded.windowTitle()
            copied_size = loaded.size()
            central = loaded.takeCentralWidget()
            self.setCentralWidget(central)
            self.setWindowTitle(copied_title)
            self.resize(copied_size) 
            loaded.deleteLater()
        else:
            self.setWindowTitle(loaded.windowTitle())
            self.resize(loaded.size())
            self.setCentralWidget(loaded)

    def _init_status_bar(self):
        self.statusBar().setStyleSheet("QStatusBar::item { border: none; }")
        self.status_icon = QLabel()
        self.status_label = QLabel("未连接")
        self.statusBar().addWidget(self.status_icon)
        self.statusBar().addWidget(self.status_label)
        self._update_status_disconnected()

        # --- 新增：为 status_icon 绑定点击事件 ---
        self.status_icon.mouseReleaseEvent = self._on_status_icon_clicked

    def _on_status_icon_clicked(self, event):
        """处理状态图标点击事件"""
        if self.status_label.text() == "已连接":
            self._log_to_ui("手动发送设备状态检测指令...")
            self.serial_worker.send_frame(const.CMD_DEVICE_STATUS_CHECK)
        else:
            self._log_to_ui("设备未连接，无法发送指令。")

    def _update_status_connected(self):
        self.status_icon.setText("🟢")
        self.status_label.setText("已连接")

    def _update_status_disconnected(self):
        self.status_icon.setText("🔴")
        self.status_label.setText("未连接")

    def _create_emoji_icon(self, emoji_char, size=64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        
        font = QFont("Segoe UI Emoji", size - 10) 
        font.setPixelSize(size - 10)
        painter.setFont(font)
        
        font_metrics = QFontMetrics(font)
        text_width = font_metrics.horizontalAdvance(emoji_char)
        text_rect = font_metrics.boundingRect(emoji_char)
        y_pos = (pixmap.height() - text_rect.height()) / 2 + font_metrics.ascent()
        x_pos = (pixmap.width() - text_width) / 2

        painter.drawText(int(x_pos), int(y_pos), emoji_char)
        painter.end()
        return QIcon(pixmap)

    def _toggle_icon(self):
        if self.is_heart_icon:
            current_icon = self.icon_white_heart
        else:
            current_icon = self.icon_heart
        
        self.setWindowIcon(current_icon)
        self.tray_icon.setIcon(current_icon)
        self.is_heart_icon = not self.is_heart_icon

    def _handle_tray_activation(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def _is_detection_in_progress(self) -> bool:
        # 检测中：有超时定时器或倒计时定时器在运行
        return (self.detection_timeout_timer.isActive() or
                (hasattr(self, 'countdown_timer') and self.countdown_timer.isActive()))

    def _reset_detection_state(self):
        """将与健康检测相关的UI和计时器重置到初始状态。"""
        self._stop_blinking()
        self._stop_countdown()
        if self.detection_timeout_timer.isActive():
            self.detection_timeout_timer.stop()
        if self.start_button:
            self.start_button.setEnabled(True)
            self.start_button.setText("开始体检")

    def _start_blinking(self):
        self._log_to_ui("开始闪烁...")
        if not self.blink_timer.isActive():
            self.blink_timer.start()

    def _stop_blinking(self):
        if self.blink_timer.isActive():
            self.blink_timer.stop()
            self.setWindowIcon(self.icon_heart)
            self.tray_icon.setIcon(self.icon_heart)
            self.is_heart_icon = False
            self._log_to_ui("停止闪烁。")

    def show_window(self):
        # 恢复窗口时，若仍在检测中则保持闪烁
        if not self._is_detection_in_progress():
            self._stop_blinking()
        self.show()
        self.activateWindow()

    def hide_window(self):
        self.hide()

    def exit_app(self):
        self.tray_icon.hide()
        self._shutdown_cleanup()
        QApplication.quit()

    def closeEvent(self, event):
        # 点击窗口右上角关闭按钮时，最小化到托盘，不退出应用、不断开串口
        self._log_to_ui("已最小化到托盘。通过托盘图标可再次打开，或选择退出。")
        event.ignore()
        self.hide_window()

    def _shutdown_cleanup(self):
        """退出应用前的资源清理：断开串口并停止线程。"""
        try:
            self.serial_worker.disconnect_serial()
        except Exception:
            pass
        try:
            if self.serial_thread.isRunning():
                self.serial_thread.quit()
                if not self.serial_thread.wait(1000):
                    self._log_to_ui("警告: 串口线程未能正常停止。")
        except Exception:
            pass
