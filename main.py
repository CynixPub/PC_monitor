import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    main_window = MainWindow()
    # To show the main window on startup, uncomment the following line
    #main_window.show()
    
    sys.exit(app.exec())
