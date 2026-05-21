import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

app = QApplication(sys.argv)

# 👉 替换成你的 ui 文件路径
ui_file = QFile("test.ui")
ui_file.open(QFile.ReadOnly)

loader = QUiLoader()
window = loader.load(ui_file)
ui_file.close()

window.show()

sys.exit(app.exec())