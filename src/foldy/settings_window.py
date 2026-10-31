"""The settings window: appearance sliders, behaviour switches, sort control and the footer buttons."""
from PyQt6.QtCore import QEasingCurve, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton, QSlider, QToolButton,
                             QVBoxLayout, QWidget)
from .constants import AUTHOR, GITHUB, VERSION
from .controls import Segmented, Toggle, update_pixmap
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

SORTS = [("newest", "Newest"), ("name", "A–Z"), ("folders", "Folders first")]

DROPS = [("smart", "Smart"), ("move", "Move"), ("copy", "Copy")]


class ToggleRow(QWidget):
    """Title + small hint on the left, a switch on the right. Clicking anywhere on the row flips the switch."""
    def __init__(self, title, hint, on_change):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle = Toggle()
        self.toggle.toggled.connect(on_change)
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
        col = QVBoxLayout(); col.setSpacing(0)
        t = QLabel(title)
        h = QLabel(hint); h.setObjectName("hint"); h.setWordWrap(True)
        for w in (t, h):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        col.addWidget(t); col.addWidget(h)
        lay.addLayout(col, 1); lay.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.toggle.click()


class SettingsWindow(QWidget):
    """Compact settings in two cards. Minimizable, sizes itself to fit."""
    def __init__(self, hub):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint |
                         Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.hub, self.update_info = hub, None
        self.setWindowTitle("Foldy Settings")
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(COMPACT_QSS)
        root = QVBoxLayout(self)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)      # hugs its content: no wasted space
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(12)

        # ---- header
        head = QHBoxLayout(); head.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(QPixmap(asset("foldy.png")).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(40, 40)                                   # the label must not grow wider than the icon
        titles = QVBoxLayout(); titles.setSpacing(0); titles.setAlignment(Qt.AlignmentFlag.AlignLeft)
        t = QLabel("Foldy"); t.setObjectName("title")
        self.status = QLabel("Fan stacks for your taskbar"); self.status.setObjectName("sub")
        self.status.setWordWrap(True); self.status.setMaximumWidth(400)
        t.setAlignment(Qt.AlignmentFlag.AlignLeft); self.status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        titles.addWidget(t); titles.addWidget(self.status)
        right = QVBoxLayout(); right.setSpacing(3)
        pill = QLabel(f"v{VERSION}"); pill.setObjectName("pill")
        by = QLabel(f'by <a style="color:#4cc9ff;text-decoration:none" href="{GITHUB}">{AUTHOR}</a>')
        by.setObjectName("foot"); by.setOpenExternalLinks(True)
        right.addWidget(pill, alignment=Qt.AlignmentFlag.AlignRight); right.addWidget(by, alignment=Qt.AlignmentFlag.AlignRight)
        head.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop); head.addLayout(titles, 1); head.addLayout(right)
        root.addLayout(head)

        # ---- appearance
        card, lay = self.card("APPEARANCE")
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
        self.sliders, self.vals, self.resets = {}, {}, {}
        for n, (key, label, lo, hi, scale, fmt) in enumerate(SLIDERS):
            r, c = n % 3, (n // 3) * 5                                  # 3 rows x 2 column groups
            sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(lo, hi); sl.setMinimumWidth(120)
            val = QLabel(); val.setObjectName("val"); val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rst = QToolButton(); rst.setObjectName("rst"); rst.setText("↺"); rst.setToolTip("Reset to default")
            rst.setCursor(Qt.CursorShape.PointingHandCursor)
            rst.clicked.connect(lambda _=False, k=key, w=sl, sc=scale: w.setValue(int(round(DEFAULTS[k] * sc))))
            sl.valueChanged.connect(lambda v, k=key, sc=scale, fm=fmt, vl=val: self.on_slider(k, v, sc, fm, vl))
            grid.addWidget(QLabel(label), r, c); grid.addWidget(sl, r, c + 1)
            grid.addWidget(val, r, c + 2); grid.addWidget(rst, r, c + 3)
            self.sliders[key], self.vals[key], self.resets[key] = sl, val, rst
        grid.setColumnMinimumWidth(4, 22)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(6, 1)
        lay.addLayout(grid)
        root.addWidget(card)

        # ---- behaviour
        card, lay = self.card("BEHAVIOUR")
        sort_row = QHBoxLayout(); sort_row.setSpacing(10)
        lbl = QVBoxLayout(); lbl.setSpacing(0)
        sl_ = QLabel("Sort by"); sh = QLabel("Order of the items in every fan"); sh.setObjectName("hint")
        lbl.addWidget(sl_); lbl.addWidget(sh)
        self.sort = Segmented(SORTS)
        self.sort.changed.connect(lambda k: self.on_set("sort", k))
        sort_row.addLayout(lbl, 1); sort_row.addWidget(self.sort)
        lay.addLayout(sort_row)
        drop_row = QHBoxLayout(); drop_row.setSpacing(10)
        lbl = QVBoxLayout(); lbl.setSpacing(0)
        dl = QLabel("Files dropped on a button")
        dh = QLabel("Onto a pinned button · Ctrl copies, Shift moves"); dh.setObjectName("hint")
        lbl.addWidget(dl); lbl.addWidget(dh)
        self.drop = Segmented(DROPS)
        self.drop.changed.connect(lambda k: self.on_set("dropmode", k))
        drop_row.addLayout(lbl, 1); drop_row.addWidget(self.drop)
        lay.addLayout(drop_row)
        sep = QFrame(); sep.setObjectName("sep"); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)
        opts = QGridLayout(); opts.setHorizontalSpacing(26); opts.setVerticalSpacing(10)
        self.r_labels = ToggleRow("Always show names", "Labels beside every icon", lambda v: self.on_set("labels", v))
        self.r_natural = ToggleRow("Natural scrolling", "Content follows your fingers", lambda v: self.on_set("natural", v))
        self.r_sub = ToggleRow("Folders inside folders", "Open sub-folders in the fan, with a back button",
                               lambda v: self.on_set("subfolders", v))
        self.r_auto = ToggleRow("Start with Windows", "Keeps your taskbar buttons instant", set_autostart)
        self.r_update = ToggleRow("Update automatically", "Asks you first when a new version is out",
                                  lambda v: self.on_set("autoupdate", v))
        check = QPushButton("Check for updates"); check.setObjectName("ghost")
        check.setCursor(Qt.CursorShape.PointingHandCursor)
        check.clicked.connect(lambda *_: hub.check_updates(manual=True))
        opts.addWidget(self.r_labels, 0, 0); opts.addWidget(self.r_natural, 0, 1)
        opts.addWidget(self.r_sub, 1, 0); opts.addWidget(self.r_auto, 1, 1)
        opts.addWidget(self.r_update, 2, 0); opts.addWidget(check, 2, 1, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        opts.setColumnStretch(0, 1); opts.setColumnStretch(1, 1)
        lay.addLayout(opts)
        root.addWidget(card)

        # ---- footer
        btns = QHBoxLayout(); btns.setSpacing(8)
        prev = QPushButton("Preview fan"); prev.setObjectName("accent"); prev.clicked.connect(lambda *_: hub.preview())
        add = QPushButton("Add folder…"); add.clicked.connect(lambda *_: hub.add_folder())
        self.btn_update = QPushButton("Update"); self.btn_update.setObjectName("update")
        self.btn_update.setIcon(QIcon(update_pixmap(16, QColor(6, 34, 46)))); self.btn_update.setIconSize(QSize(16, 16))
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.clicked.connect(lambda *_: hub.begin_update())
        self.btn_update.hide()
        reset = QPushButton("Reset all"); reset.clicked.connect(self.reset)
        un = QPushButton(" Uninstall"); un.setObjectName("danger")
        un.setIcon(QIcon(trash_pixmap(16, QColor(255, 140, 152), dpr=2.0))); un.setIconSize(QSize(16, 16))
        un.clicked.connect(lambda *_: hub.open_uninstall())
        btns.addWidget(prev); btns.addWidget(add); btns.addStretch()
        btns.addWidget(self.btn_update); btns.addWidget(reset); btns.addWidget(un)       # the update button spawns left of Reset all
        root.addLayout(btns)
        self.sync()

    def card(self, title):
        f = QFrame(); f.setObjectName("card")
        lay = QVBoxLayout(f); lay.setContentsMargins(16, 12, 16, 14); lay.setSpacing(10)
        s = QLabel(title); s.setObjectName("sec")
        lay.addWidget(s)
        return f, lay

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
        self.sort.set_value(S["sort"], animate=False)
        self.drop.set_value(S["dropmode"], animate=False)
        for row, v in ((self.r_labels, S["labels"]), (self.r_natural, S["natural"]), (self.r_sub, S["subfolders"]),
                       (self.r_auto, autostart_enabled()), (self.r_update, S["autoupdate"])):
            row.toggle.set_value(v)

    def set_update(self, info):
        """Show (or hide) the green update button next to 'Reset all'. It slides open the first time it appears."""
        self.update_info = info
        b = self.btn_update
        if info is None:
            b.hide()
            return
        b.setText(f" Update to v{info['version']}")
        b.setToolTip(f"Download and install Foldy v{info['version']} (you have v{VERSION})")
        if not b.isHidden():
            return
        b.setMaximumWidth(0)
        b.show()
        target = b.sizeHint().width()
        self._grow = QVariantAnimation(self)
        self._grow.setDuration(420)
        self._grow.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutBack))
        self._grow.setStartValue(0); self._grow.setEndValue(target)
        self._grow.valueChanged.connect(lambda v: b.setMaximumWidth(max(0, int(v))))
        self._grow.finished.connect(lambda: b.setMaximumWidth(16777215))
        self._grow.start()

    def reset(self):
        S.update(DEFAULTS)
        self.sync()
        self.hub.settings_changed()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
