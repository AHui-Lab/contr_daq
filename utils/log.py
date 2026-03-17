import logging
from PySide6.QtCore import QObject, Signal


# -------------------------------
# Qt → UI 通道
# -------------------------------
class _UILogger(QObject):
    log_signal = Signal(str)

    def emit(self, msg: str):
        self.log_signal.emit(msg)


_ui_logger = _UILogger()


class _QtLogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        _ui_logger.emit(msg)


# -------------------------------
# 全局 Logger（只初始化一次）
# -------------------------------
_logger = logging.getLogger("DAQ")
_logger.setLevel(logging.INFO)

if not _logger.handlers:
    # 控制台
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    # UI
    ui_handler = _QtLogHandler()
    ui_handler.setFormatter(logging.Formatter("%(message)s"))

    _logger.addHandler(console)
    _logger.addHandler(ui_handler)


# -------------------------------
# 给外界用的唯一接口
# -------------------------------
def bind_log_widget(widget):
    """
    在 MainWindow 中调用一次：
    bind_log_widget(self.ui.logTextEdit)
    """
    _ui_logger.log_signal.connect(widget.appendPlainText)


def log(msg: str, level="info"):
    if level == "info":
        _logger.info(msg)
    elif level == "warning":
        _logger.warning(msg)
    elif level == "error":
        _logger.error(msg)
    else:
        _logger.info(msg)
