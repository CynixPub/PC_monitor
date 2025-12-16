import sys
import ctypes
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

if __name__ == "__main__":
    # 设置 AppUserModelID 以确保任务栏图标正确显示
    myappid = 'mycompany.myproduct.subproduct.version' # 任意字符串
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    main_window = MainWindow()
    # To show the main window on startup, uncomment the following line
    main_window.show()
    
    sys.exit(app.exec())
