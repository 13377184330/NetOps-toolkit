import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.getcwd())
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication([])
from gui.tools_window import NetworkToolsWindow
t = NetworkToolsWindow()
t.show()
sys.exit(app.exec_())
