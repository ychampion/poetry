import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow


def record(**values):
    output = Path(os.environ["LAUNCH_RECEIPT"])
    output.write_text(json.dumps(dict(values, executable=sys.executable,
                                      arguments=sys.argv[1:], source=__file__)), encoding="utf-8")


def console():
    record(kind="console")


def main():
    app = QApplication([])
    window = QMainWindow()
    window.show()

    def observe():
        record(kind="gui", visible=window.isVisible())
        app.quit()

    QTimer.singleShot(100, observe)
    return app.exec()
