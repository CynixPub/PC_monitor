import struct
import serial
from serial.tools import list_ports

from PySide6.QtCore import QObject, Signal, QThread

from constants import (
    PROTO_VER, CMD_ACK, CMD_NOTIFY_HEALTH_DATA_READY, CMD_GET_LAST_HEALTH_DATA,
    CMD_GET_MOUSE_DATA
)


def crc16_xmodem(data: bytes) -> int:
    """
    A simple, correct, bit-by-bit CRC-16/XMODEM implementation.
    """
    crc = 0x0000
    poly = 0x1021
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
    return crc & 0xFFFF


class SerialWorker(QObject):
    """
    串口通信工作线程
    - 在独立线程中运行，避免阻塞 UI
    - 通过信号与主线程通信
    """
    # --- Signals ---
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)
    log_message = Signal(str)
    
    # 业务信号
    ack_received = Signal(int, int)  # original_cmd, status_code
    health_data_received = Signal(bytes)
    mouse_data_received = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.is_running = False
        self.read_buffer = b''
        
        # --- 用于自动重连 ---
        self.port_name = ""
        self.baudrate = 0
        self.auto_reconnect = True
        
        self.command_handlers = {
            CMD_ACK: self._handle_ack,
            CMD_NOTIFY_HEALTH_DATA_READY: self._handle_health_data,
            CMD_GET_LAST_HEALTH_DATA: self._handle_health_data,
            CMD_GET_MOUSE_DATA: self._handle_mouse_data,
        }

    def connect_serial(self, port_name: str, baudrate: int = 115200):
        """连接到串口"""
        self.port_name = port_name
        self.baudrate = baudrate
        
        try:
            self.serial_port = serial.Serial()
            self.serial_port.port = self.port_name
            self.serial_port.baudrate = self.baudrate
            self.serial_port.timeout = 0.1
            self.serial_port.dtr = False
            self.serial_port.rts = False
            self.serial_port.open()

            if self.serial_port.is_open:
                self.is_running = True
                self.log_message.emit(f"串口 {self.port_name} 已连接。")
                self.connected.emit()
                return True # 指示连接成功
            else:
                raise IOError("无法打开串口。")
        except serial.SerialException as e:
            available_ports = [p.device for p in list_ports.comports()]
            if available_ports:
                ports_str = ", ".join(available_ports)
                error_msg = f"连接串口 {self.port_name} 失败: {e}\n\n当前可用串口: {ports_str}"
            else:
                error_msg = f"连接串口 {self.port_name} 失败: {e}\n\n系统上未找到任何可用串口。"
            self.error_occurred.emit(error_msg)
            return False # 指示连接失败

    def disconnect_serial(self):
        """断开串口连接"""
        self.auto_reconnect = False # 用户主动断开，禁用自动重连
        self.is_running = False
        if self.serial_port and self.serial_port.is_open:
            port_name = self.serial_port.name
            self.serial_port.close()
            self.log_message.emit(f"串口 {port_name} 已断开。")
            self.disconnected.emit()

    def send_frame(self, cmd: int, payload: bytes = b''):
        """构建并发送一个数据帧"""
        if not self.serial_port or not self.serial_port.is_open:
            self.error_occurred.emit("发送失败：串口未连接。")
            return

        len_payload = len(payload)
        header = b'\xAA\x55'
        
        # 帧头之后的数据，用于 CRC 计算
        data_for_crc = struct.pack('<BBH', PROTO_VER, cmd, len_payload) + payload
        crc = crc16_xmodem(data_for_crc)
        
        frame = header + data_for_crc + struct.pack('<H', crc)

        try:
            self.serial_port.write(frame)
            self.log_message.emit(f"发送: {frame.hex(' ').upper()}")
        except serial.SerialException as e:
            self.error_occurred.emit(f"发送数据失败: {e}")

    def run(self):
        """持续读取串口数据，包含自动重连逻辑"""
        while self.is_running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    # 1. 如果串口有数据，全部读入缓冲区
                    if self.serial_port.in_waiting > 0:
                        data = self.serial_port.read(self.serial_port.in_waiting)
                        self.read_buffer += data
                    
                    # 2. 处理缓冲区中的数据，解析数据帧
                    self._process_read_data()

                except serial.SerialException as e:
                    self.error_occurred.emit(f"读取串口时出错: {e}。")
                    self.serial_port.close()
                    self.disconnected.emit()
                    # 连接丢失，进入重连逻辑
                    if self.auto_reconnect:
                        self.log_message.emit("连接已断开，将在5秒后尝试自动重连...")
                        QThread.sleep(5)
                        self._attempt_reconnect()

            QThread.msleep(20) # 适当增加延时，降低 CPU 占用

    def _attempt_reconnect(self):
        """尝试重新连接串口"""
        while self.auto_reconnect and self.is_running:
            self.log_message.emit(f"正在尝试重新连接到 {self.port_name}...")
            if self.connect_serial(self.port_name, self.baudrate):
                self.log_message.emit("重新连接成功！")
                break # 成功则退出重连循环
            else:
                self.log_message.emit("重新连接失败，将在5秒后重试...")
                QThread.sleep(5)

    def _process_read_data(self):
        """在缓冲区中循环查找并处理所有完整的数据帧"""
        while True:
            # 1. 查找帧头
            start_index = self.read_buffer.find(b'\xAA\x55')
            if start_index == -1:
                # 缓冲区中没有帧头。为防止缓冲区无限增长，只保留最后一个字节，
                # 因为它可能是下一个帧的 AA。
                if len(self.read_buffer) > 1:
                    self.read_buffer = self.read_buffer[-1:]
                return # 没有找到帧头，退出循环，等待更多数据

            # 2. 丢弃帧头之前的所有无效数据
            self.read_buffer = self.read_buffer[start_index:]
            
            # 3. 检查是否有足够的数据构成一个最小帧 (帧头+固定部分+CRC)
            # 2 (header) + 4 (ver,cmd,len) + 2 (crc) = 8 bytes
            if len(self.read_buffer) < 8:
                return # 数据不足以构成最小帧，等待更多数据
            
            # 4. 解包获取 payload 长度
            _, _, payload_len = struct.unpack('<BBH', self.read_buffer[2:6])

            # 5. 计算完整的帧长度并检查缓冲区中是否有足够的数据
            frame_len = 8 + payload_len
            if len(self.read_buffer) < frame_len:
                return # 帧不完整，等待更多数据
            
            # 6. 提取完整的数据帧
            frame = self.read_buffer[:frame_len]
            
            # 7. 从缓冲区移除已处理的帧
            self.read_buffer = self.read_buffer[frame_len:]

            # 8. 校验并处理帧
            fixed_part = frame[2:6]
            payload = frame[6:6+payload_len]
            received_crc = struct.unpack('<H', frame[6+payload_len:])[0]

            data_to_check = frame[2:6+payload_len]
            calculated_crc = crc16_xmodem(data_to_check)

            if received_crc == calculated_crc:
                proto_ver, cmd, _ = struct.unpack('<BBH', fixed_part)
                
                if proto_ver != PROTO_VER:
                    self.log_message.emit(f"警告: 协议版本不匹配 (收到 {proto_ver}, 需要 {PROTO_VER})。")
                    continue # 继续处理缓冲区中的下一个可能帧
                    
                self.log_message.emit(f"接收: CMD={hex(cmd)}, Payload={payload.hex(' ').upper()}")
                self._handle_valid_frame(cmd, payload)
            else:
                self.log_message.emit(f"警告: CRC 校验失败 (收到 {received_crc}, 计算为 {calculated_crc}) Frame: {frame.hex(' ').upper()}")
            
            # 继续循环，处理缓冲区中可能存在的下一个帧

    def _handle_valid_frame(self, cmd: int, payload: bytes):
        """处理校验通过的帧，并根据命令分发"""
        handler = self.command_handlers.get(cmd)
        if handler:
            handler(payload)
        else:
            self.log_message.emit(f"警告: 未知的命令 {hex(cmd)}。")

    def _handle_ack(self, payload: bytes):
        """处理 ACK 命令"""
        if len(payload) == 2:
            original_cmd, status_code = struct.unpack('<BB', payload)
            self.ack_received.emit(original_cmd, status_code)
        else:
            self.log_message.emit("警告: ACK 帧的 payload 长度不正确。")

    def _handle_health_data(self, payload: bytes):
        """处理健康数据"""
        self.health_data_received.emit(payload)

    def _handle_mouse_data(self, payload: bytes):
        """处理鼠标数据"""
        self.mouse_data_received.emit(payload)
