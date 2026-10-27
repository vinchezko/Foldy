"""The compact settings window."""
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
                             QPushButton, QSlider, QToolButton, QVBoxLayout, QWidget)
from .constants import AUTHOR, GITHUB, VERSION
from .settings import DEFAULTS, S
from .styles import COMPACT_QSS
from .widgets import trash_pixmap
from .winutil import asset, autostart_enabled, dark_titlebar, set_autostart


SLIDERS = [                                    # key, label, min, max, scale, value formatter
    ("density", "Density", 70, 140, 100, lambda v: f"{v}%"),
    ("speed", "Animation speed", 50, 200, 100, lambda v: f"{v / 100:.1f}×"),
    ("glass", "Glass opacity", 25, 100, 100, lambda v: f"{v}%"),
    ("magnify", "Magnification", 0, 80, 100, lambda v: f"{v}%"),
    ("curve", "Arc curve", 0, 100, 100, lambda v: f"{v}%"),
    ("maxvis", "Max items", 6, 20, 1, lambda v: f"{v}"),
]


class SettingsWindow(QWidget):
    """Compact settings: two slider columns, one row of options, one row of buttons. Minimizable, sizes itself to fit."""
    def __init__(self, hub):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint |
                         Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.hub = hub
        self.setWindowTitle("Foldy Settings")
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(COMPACT_QSS)
        root = QVBoxLayout(self)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)      # hugs its content: no wasted space
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        head = QHBoxLayout(); head.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(asset("foldy.png")).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation))
        titles = QVBoxLayout(); titles.setSpacing(0)
        t = QLabel("Foldy"); t.setObjectName("title")
        self.status = QLabel("Fan stacks for your taskbar"); self.status.setObjectName("sub")
        self.status.setWordWrap(True); self.status.setMaximumWidth(380)
        titles.addWidget(t); titles.addWidget(self.status)
        by = QLabel(f'v{VERSION} · by <a style="color:#4cc9ff;text-decoration:none" href="{GITHUB}">{AUTHOR}</a>')
        by.setObjectName("foot"); by.setOpenExternalLinks(True)
        head.addWidget(logo); head.addLayout(titles); head.addStretch(); head.addWidget(by, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)
        root.addWidget(self.sep())

        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6)
        self.sliders, self.vals, self.resets = {}, {}, {}
        for n, (key, label, lo, hi, scale, fmt) in enumerate(SLIDERS):
            r, c = n % 3, (n // 3) * 5                                  # 3 rows x 2 column groups
            sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(lo, hi); sl.setMinimumWidth(110)
            val = QLabel(); val.setObjectName("val"); val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rst = QToolButton(); rst.setObjectName("rst"); rst.setText("↺"); rst.setToolTip("Reset to default")
            rst.setCursor(Qt.CursorShape.PointingHandCursor)
            rst.clicked.connect(lambda _=False, k=key, w=sl, sc=scale: w.setValue(int(round(DEFAULTS[k] * sc))))
            sl.valueChanged.connect(lambda v, k=key, sc=scale, fm=fmt, vl=val: self.on_slider(k, v, sc, fm, vl))
            grid.addWidget(QLabel(label), r, c); grid.addWidget(sl, r, c + 1)
            grid.addWidget(val, r, c + 2); grid.addWidget(rst, r, c + 3)
            self.sliders[key], self.vals[key], self.resets[key] = sl, val, rst
        grid.setColumnMinimumWidth(4, 16)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(6, 1)
        root.addLayout(grid)
        root.addWidget(self.sep())

        opts = QGridLayout(); opts.setHorizontalSpacing(16); opts.setVerticalSpacing(6)
        sort_row = QHBoxLayout(); sort_row.setSpacing(8)
        self.sort = QComboBox()
        for key, text in (("newest", "Newest first"), ("name", "Name (A–Z)"), ("folders", "Folders first")):
            self.sort.addItem(text, key)
        self.sort.currentIndexChanged.connect(lambda _: self.on_set("sort", self.sort.currentData()))
        sort_row.addWidget(QLabel("Sort by")); sort_row.addWidget(self.sort); sort_row.addStretch()
        self.cb_labels = self.check("Always show names", lambda v: self.on_set("labels", v))
        self.cb_natural = self.check("Natural scrolling", lambda v: self.on_set("natural", v))
        self.cb_auto = self.check("Start with Windows", set_autostart)
        opts.addLayout(sort_row, 0, 0); opts.addWidget(self.cb_auto, 0, 1)
        opts.addWidget(self.cb_labels, 1, 0); opts.addWidget(self.cb_natural, 1, 1)
        root.addLayout(opts)

        btns = QHBoxLayout(); btns.setSpacing(8)
        prev = QPushButton("Preview fan"); prev.setObjectName("accent"); prev.clicked.connect(lambda *_: hub.preview())
        add = QPushButton("Add folder…"); add.clicked.connect(lambda *_: hub.add_folder())
        reset = QPushButton("Reset all"); reset.clicked.connect(self.reset)
        un = QPushButton(" Uninstall"); un.setObjectName("danger")
        un.setIcon(QIcon(trash_pixmap(16, QColor(255, 140, 152), dpr=2.0))); un.setIconSize(QSize(16, 16))
        un.clicked.connect(lambda *_: hub.open_uninstall())
        btns.addWidget(prev); btns.addWidget(add); btns.addStretch(); btns.addWidget(reset); btns.addWidget(un)
        root.addLayout(btns)
        self.sync()

    def sep(self):
        f = QFrame(); f.setObjectName("sep"); f.setFrameShape(QFrame.Shape.HLine)
        return f

    def check(self, text, cb):
        c = QCheckBox(text)
        c.toggled.connect(cb)
        return c

    def on_slider(self, key, v, scale, fmt, label):
        label.setText(fmt(v))
        self.resets[key].setEnabled(v != int(round(DEFAULTS[key] * scale)))
        self.on_set(key, v / scale if scale != 1 else v)

    def on_set(self, key, value):
        if S.get(key) != value:
            S[key] = value
            self.hub.settings_changed()

    def sync(self):
        """Push the current settings into the widgets without triggering change handlers."""
        for key, label, lo, hi, scale, fmt in SLIDERS:
            sl = self.sliders[key]
            sl.blockSignals(True); sl.setValue(int(round(S[key] * scale))); sl.blockSignals(False)
            self.vals[key].setText(fmt(sl.value()))
            self.resets[key].setEnabled(sl.value() != int(round(DEFAULTS[key] * scale)))
        self.sort.blockSignals(True); self.sort.setCurrentIndex(max(0, self.sort.findData(S["sort"]))); self.sort.blockSignals(False)
        for cb, v in ((self.cb_labels, S["labels"]), (self.cb_natural, S["natural"]), (self.cb_auto, autostart_enabled())):
            cb.blockSignals(True); cb.setChecked(bool(v)); cb.blockSignals(False)

    def reset(self):
        S.update(DEFAULTS)
        self.sync()
        self.hub.settings_changed()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
