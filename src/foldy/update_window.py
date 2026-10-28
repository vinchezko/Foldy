"""The 'A new version is ready' window (Update now / Later)."""
import re
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .constants import VERSION
from .styles import SETTINGS_QSS
from .winutil import asset, center_on_screen, dark_titlebar


def plain_notes(md, max_lines=7):
    """GitHub release notes (Markdown) -> a few readable plain lines."""
    out = []
    for line in str(md or "").splitlines():
        t = re.sub(r"[`*_>#]+", "", line).strip()
        t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
        if t:
            out.append(("• " + t.lstrip("-+ ").strip()) if line.lstrip().startswith(("-", "*", "+")) else t)
        if len(out) >= max_lines:
            out.append("…")
            break
    return "\n".join(out)


class UpdatePrompt(QWidget):
    """Asks, never forces: 'Update now' or 'Later'. Closing the window counts as Later."""
    now, later = pyqtSignal(), pyqtSignal()

    def __init__(self, info, can_install=True):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.decided = False
        self.setWindowTitle("Foldy update")
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(SETTINGS_QSS + "QLabel{background:transparent;}QFrame#notes{background:#23252d;border:1px solid #2f323b;border-radius:10px;}")
        self.setFixedWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(12)
        head = QHBoxLayout(); head.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(QPixmap(asset("foldy.png")).scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        titles = QVBoxLayout(); titles.setSpacing(2)
        t = QLabel("A new version of Foldy is ready"); t.setObjectName("title2"); t.setWordWrap(True)
        v = QLabel(f"v{VERSION}  →  <b style='color:#4cc9ff'>v{info['version']}</b>"); v.setObjectName("sub")
        titles.addWidget(t); titles.addWidget(v)
        head.addWidget(logo); head.addLayout(titles, 1)
        root.addLayout(head)
        notes = plain_notes(info.get("notes"))
        if notes:
            box = QFrame(); box.setObjectName("notes")
            bl = QVBoxLayout(box); bl.setContentsMargins(14, 10, 14, 10)
            n = QLabel(notes); n.setWordWrap(True); n.setStyleSheet("color:#c8ccd6;")
            bl.addWidget(n)
            root.addWidget(box)
        sub = QLabel("Foldy downloads the update, checks it, closes itself and reopens as the new version. Your folders and settings stay as they are."
                     if can_install else "Open the release page to download the new version.")
        sub.setObjectName("sub"); sub.setWordWrap(True)
        root.addWidget(sub)
        row = QHBoxLayout(); row.setSpacing(8)
        later = QPushButton("Later"); later.clicked.connect(self.close)
        go = QPushButton("Update now" if can_install else "Open release page"); go.setObjectName("accent"); go.setDefault(True)
        go.clicked.connect(self.accept)
        row.addStretch(); row.addWidget(later); row.addWidget(go)
        root.addLayout(row)

    def accept(self):
        self.decided = True
        self.now.emit()
        self.close()

    def closeEvent(self, e):
        if not self.decided:
            self.decided = True
            self.later.emit()
        super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
        QTimer.singleShot(0, lambda: center_on_screen(self))
