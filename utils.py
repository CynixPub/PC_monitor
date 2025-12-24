import sys
import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QFontMetrics
from PySide6.QtCore import Qt

def resource_path(relative_path):
    """
    获取资源的绝对路径。
    无论是在开发环境（作为 .py 运行）还是在打包后（作为 .exe 运行），这个函数都能正常工作。
    """
    try:
        # PyInstaller 会创建一个临时文件夹，并将其路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        # 在开发环境中，_MEIPASS 不存在，所以我们使用当前文件的路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def user_data_path(relative_path):
    """
    获取用户可写数据文件的绝对路径。
    - 对于打包后的应用，这通常是 .exe 文件所在的目录。
    - 对于开发环境，这是项目的根目录。
    """
    if getattr(sys, 'frozen', False):
        # 程序被打包了（例如通过 PyInstaller）
        base_path = os.path.dirname(sys.executable)
    else:
        # 正常在开发环境中运行
        base_path = os.path.abspath(".")
        
    return os.path.join(base_path, relative_path)

def create_emoji_icon(emoji_char, size=64):
    """创建一个基于 Emoji 的 QIcon"""
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
