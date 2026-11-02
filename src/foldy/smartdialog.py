"""'New smart stack' window: a stack whose contents come from a rule (newest files, recent files, only pictures...)
instead of from one literal folder."""
import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit,
                             QPushButton, QSlider, QVBoxLayout, QWidget)
from .controls import Segmented
from .styles import COMPACT_QSS
from .winutil import asset, dark_titlebar


HOME = os.path.expanduser("~")
PLACES = [("@recent", "Recent (Windows)"), (os.path.join(HOME, "Downloads"), "Downloads"),
          (os.path.join(HOME, "Desktop"), "Desktop"), (os.path.join(HOME, "Documents"), "Documents"),
          (os.path.join(HOME, "Pictures"), "Pictures"), (os.path.join(HOME, "Videos"), "Videos"),
          (os.path.join(HOME, "Music"), "Music")]
KINDS = [("all", "Anything"), ("pictures", "Pictures"), ("videos", "Videos"), ("documents", "Documents"), ("audio", "Audio")]
AGES = [("0", "Any time"), ("1", "Today"), ("7", "7 days"), ("30", "30 days")]
KIND_NOTES = {"all": "any kind of file", "pictures": "pictures", "videos": "videos",
              "documents": "documents", "audio": "audio"}

QSS = COMPACT_QSS + """
QLineEdit{background:#2a2c34;border:1px solid #3d404a;border-radius:8px;padding:6px 10px;selection-background-color:#4cc9ff;}
QLineEdit:focus{border-color:#4cc9ff;}
QLabel#note{color:#8fb7cc;font-size:11px;}
QCheckBox{spacing:8px;background:transparent;}
"""

PRESETS = [
    ("Recent files", {"name": "Recent files", "sources": ["@recent"], "kind": "all", "days": 0, "limit": 20, "recursive": False}),
    ("Newest 20 downloads", {"name": "Newest 20 downloads", "sources": [PLACES[1][0]], "kind": "all", "days": 0, "limit": 20,
                             "recursive": False}),
    ("Recent pictures", {"name": "Recent pictures", "sources": [PLACES[4][0], PLACES[1][0], PLACES[2][0]], "kind": "pictures",
                         "days": 30, "limit": 30, "recursive": True}),
]


class SmartDialog(QWidget):
    created = pyqtSignal(dict)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint |
                         Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("New smart stack")
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(QSS)
        self.boxes = {}                                             # source path -> its checkbox
        root = QVBoxLayout(self)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        root.setContentsMargins(18, 14, 18, 16); root.setSpacing(12)

        t = QLabel("New smart stack"); t.setObjectName("title")
        s = QLabel("A stack made from a rule, not from one folder. It refreshes every time you open it."); s.setObjectName("sub")
        root.addWidget(t); root.addWidget(s)

        quick = QHBoxLayout(); quick.setSpacing(8)
        q = QLabel("Quick start"); q.setObjectName("hint")
        quick.addWidget(q)
        for label, spec in PRESETS:
            b = QPushButton(label); b.setObjectName("ghost"); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, sp=spec: self.load(sp))
            quick.addWidget(b)
        quick.addStretch()
        root.addLayout(quick)

        card = QFrame(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(16, 12, 16, 14); lay.setSpacing(10)
        lay.addWidget(self.sec("NAME"))
        self.name = QLineEdit(); self.name.setPlaceholderText("Leave empty to name it automatically")
        self.name.setMaxLength(60)
        lay.addWidget(self.name)

        lay.addWidget(self.sec("TAKE FILES FROM"))
        self.grid = QGridLayout(); self.grid.setHorizontalSpacing(18); self.grid.setVerticalSpacing(6)
        for path, label in PLACES:
            self.add_box(path, label)
        lay.addLayout(self.grid)
        more = QHBoxLayout()
        add = QPushButton("Add folder…"); add.setObjectName("ghost"); add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self.pick)
        more.addWidget(add); more.addStretch()
        lay.addLayout(more)

        lay.addWidget(self.sec("WHICH FILES"))
        self.kind = Segmented(KINDS)
        self.age = Segmented(AGES)
        row = QHBoxLayout(); row.setSpacing(10)
        lk = QLabel("Type"); lk.setMinimumWidth(70)
        row.addWidget(lk); row.addWidget(self.kind); row.addStretch()
        lay.addLayout(row)
        row = QHBoxLayout(); row.setSpacing(10)
        la = QLabel("Changed"); la.setMinimumWidth(70)
        row.addWidget(la); row.addWidget(self.age); row.addStretch()
        lay.addLayout(row)
        row = QHBoxLayout(); row.setSpacing(10)
        lc = QLabel("How many"); lc.setMinimumWidth(70)
        self.limit = QSlider(Qt.Orientation.Horizontal); self.limit.setRange(5, 50); self.limit.setMinimumWidth(220)
        self.limit_val = QLabel(); self.limit_val.setObjectName("val")
        self.limit.valueChanged.connect(lambda v: (self.limit_val.setText(str(v)), self.refresh_note()))
        row.addWidget(lc); row.addWidget(self.limit, 1); row.addWidget(self.limit_val)
        lay.addLayout(row)
        self.deep = QCheckBox("Look inside sub-folders too (up to 3 levels)")
        self.deep.toggled.connect(lambda _=False: self.refresh_note())
        lay.addWidget(self.deep)
        self.note = QLabel(); self.note.setObjectName("note")
        lay.addWidget(self.note)
        root.addWidget(card)

        btns = QHBoxLayout(); btns.setSpacing(8)
        self.err = QLabel(""); self.err.setObjectName("note"); self.err.setStyleSheet("color:#ff8c98;")
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.close)
        go = QPushButton("Create && pin to taskbar"); go.setObjectName("accent")
        go.setCursor(Qt.CursorShape.PointingHandCursor); go.clicked.connect(self.submit)
        btns.addWidget(self.err, 1); btns.addWidget(cancel); btns.addWidget(go)
        root.addLayout(btns)

        for w in (self.kind, self.age):
            w.changed.connect(lambda _k: self.refresh_note())
        self.load(PRESETS[1][1])

    @staticmethod
    def sec(text):
        s = QLabel(text); s.setObjectName("sec")
        return s

    def add_box(self, path, label, checked=False):
        if path in self.boxes:
            self.boxes[path].setChecked(True)
            return
        cb = QCheckBox(label)
        cb.setToolTip(path if path != "@recent" else "The files Windows lists under Recent")
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setChecked(checked)
        cb.toggled.connect(lambda _=False: self.refresh_note())
        n = len(self.boxes)
        self.grid.addWidget(cb, n // 4, n % 4)
        self.boxes[path] = cb

    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "Add a folder to take files from", HOME)
        if d:
            d = os.path.normpath(d)
            self.add_box(d, os.path.basename(d) or d, True)

    def sources(self):
        return [p for p, cb in self.boxes.items() if cb.isChecked()]

    def load(self, spec):
        """Fill every control from a spec (a quick-start button)."""
        for p in spec["sources"]:
            if p not in self.boxes and p != "@recent":
                self.add_box(p, os.path.basename(p) or p)
        for p, cb in self.boxes.items():
            cb.setChecked(p in spec["sources"])
        self.name.setText(spec.get("name", ""))
        self.kind.set_value(spec.get("kind", "all"), animate=False)
        self.age.set_value(str(spec.get("days", 0)), animate=False)
        self.limit.setValue(int(spec.get("limit", 20)))
        self.limit_val.setText(str(self.limit.value()))
        self.deep.setChecked(bool(spec.get("recursive")))
        self.refresh_note()

    def spec(self):
        return {"name": self.name.text().strip() or self.auto_name(), "sources": self.sources(), "kind": self.kind.value(),
                "days": int(self.age.value()), "limit": self.limit.value(), "recursive": self.deep.isChecked()}

    def auto_name(self):
        src = self.sources()
        kind = self.kind.value()
        what = "files" if kind == "all" else kind
        if src == ["@recent"]:
            return "Recent " + what
        place = os.path.basename(src[0].rstrip("\\/")) if len(src) == 1 and src[0] != "@recent" else ""
        return f"Newest {self.limit.value()} {what}" + (f" in {place}" if place else "")

    def refresh_note(self):
        days = int(self.age.value())
        when = {0: "", 1: ", changed today", 7: ", changed in the last 7 days", 30: ", changed in the last 30 days"}[days]
        n = len(self.sources())
        self.note.setText(f"Shows the newest {self.limit.value()}: {KIND_NOTES[self.kind.value()]}{when}, from {n} "
                          f"place{'s' if n != 1 else ''}.")
        self.err.setText("")

    def submit(self):
        if not self.sources():
            self.err.setText("Pick at least one place to take files from.")
            return
        self.created.emit(self.spec())
        self.close()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
