import struct
from typing import Tuple

from PySide6.QtWidgets import QApplication


class MouseDataProcessor:
    """
    负责解析设备鼠标数据 payload、进行像素到物理长度(米)转换，并持久化累计值。
    数据库存储仍以像素为单位；界面展示转换为米，保留三位小数。
    """

    def __init__(self, db_handler):
        self.db_handler = db_handler
        self._dpi = self._get_screen_dpi()

    def _get_screen_dpi(self) -> float:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 96.0
        dpi = screen.physicalDotsPerInch()
        # 兜底
        if dpi is None or dpi <= 0:
            dpi = 96.0
        print(f"屏幕DPI: {dpi}")
        return float(dpi)

    def parse_payload(self, payload: bytes) -> Tuple[int, int, int, int]:
        """
        支持两种格式：
        - <IIII>: distance_px, left, right, mid (16字节) - 注意：right和mid在数据中是交换的
        - <II>: distance_px, left (8字节)，mid/right 置 0
        返回像素单位的累计值。
        """
        if len(payload) >= 16:
            distance, left, right, mid = struct.unpack('<IIII', payload[:16])
        elif len(payload) == 8:
            distance, left = struct.unpack('<II', payload)
            mid, right = 0, 0
        else:
            raise ValueError(f"鼠标数据 payload 长度不正确: {len(payload)}")
        return int(distance), int(left), int(mid), int(right)

    def pixels_to_mm(self, pixels: int) -> float:
        # 1 inch = 25.4 mm
        return float(pixels) * 25.4 / self._dpi

    def pixels_to_meters_str(self, pixels: int) -> str:
        meters = self.pixels_to_mm(pixels) / 1000.0
        return f"{meters:.3f} 米"

    def process_payload(self, payload: bytes) -> dict:
        distance_px, left, mid, right = self.parse_payload(payload)
        # 落库（像素）
        self.db_handler.save_or_update_mouse_data(distance_px, left, mid, right)
        return {
            'distance_px': distance_px,
            'left_click': left,
            'mid_click': mid,
            'right_click': right,
            'distance_m_str': self.pixels_to_meters_str(distance_px),
        }


