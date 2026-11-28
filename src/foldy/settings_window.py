"""The settings window: a sidebar with five pages (Appearance, Behaviour, Features, Stacks, Updates & about) instead of one
long wall of controls. Everything applies instantly; 'Preview fan' is always one click away at the bottom."""
import html, os
from PyQt6.QtCore import QSize, QTimer, QUrl, Qt
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
                             QStackedWidget, QToolButton, QVBoxLayout, QWidget, QMessageBox)
from .constants import AUTHOR, FEEDBACK_URL, GITHUB, VERSION
from .controls import Segmented, Toggle, update_pixmap
from . import iconstyle
from .icon_editor import IconEditor
from .render import real_folder, smart_spec
from .settings import DEFAULTS, S
from .shortcuts import folder_id, stack_style
from .styles import SIDEBAR_QSS
from .widgets import palette_pixmap, trash_pixmap
from .winutil import asset, autostart_enabled, dark_titlebar, data_dir, open_path, set_autostart


SLIDERS = [                                    # key, label, hint, min, max, scale, value formatter
    ("density", "Density", "How big icons and spacing are", 70, 140, 100, lambda v: f"{v}%"),
    ("speed", "Animation speed", "How fast it opens and folds", 50, 200, 100, lambda v: f"{v / 100:.1f}×"),
    ("glass", "Glass opacity", "How solid the name pills look", 25, 100, 100, lambda v: f"{v}%"),
    ("magnify", "Magnification", "How much the hovered icon grows", 0, 80, 100, lambda v: f"{v}%"),
    ("curve", "Arc curve", "Straight column to deep curve", 0, 100, 100, lambda v: f"{v}%"),
    ("maxvis", "Max items", "Items shown before you scroll", 6, 20, 1, lambda v: f"{v}"),
]

SORTS = [("newest", "Newest"), ("name", "A–Z"), ("folders", "Folders first")]
DROPS = [("smart", "Smart"), ("move", "Move"), ("copy", "Copy")]

SORT_NOTES = {                                 # shown under the chooser: what the selected option does
    "newest": "Newest first: what changed last sits right next to the taskbar.",
    "name": "A to Z by name, with folders and files mixed together.",
    "folders": "Folders first, then files, each group A to Z.",
}
DROP_NOTES = {
    "smart": "Smart: moves within one drive, copies from another drive (like Explorer).",
    "move": "Move: dropped files are moved into the folder. Hold Ctrl to copy instead.",
    "copy": "Copy: dropped files are copied into the folder. Hold Shift to move instead.",
}

PAGES = [("appearance", "Appearance", "Look and feel of the fan"),
         ("behaviour", "Behaviour", "How the fan sorts, scrolls and takes files"),
         ("features", "Features", "Extras you can switch on or off"),
         ("stacks", "Stacks", "The folders you have pinned"),
         ("about", "Updates & about", "Version, start-up and housekeeping")]

KEYS = [("↑  ↓", "Move through the items"), ("Enter", "Open the selected item"), ("Shift+Enter", "Show it in Explorer"),
        ("→", "Dive into a folder"), ("←  Backspace", "Go back up"), ("Esc", "Clear the search, then close"),
        ("Type", "Filter by name"), ("Right-click", "Open, Open with, Show in Explorer, Copy path")]


class ToggleRow(QWidget):
    """Title + small hint on the left, a switch on the right. The hint follows the switch. Clicking the row flips it."""
    def __init__(self, title, hint, on_change, hint_off=None):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hint_on, self.hint_off = hint, hint_off or hint
        self.toggle = Toggle()
        self.toggle.toggled.connect(on_change)
        self.toggle.toggled.connect(self.show_hint)
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 2, 0, 2); lay.setSpacing(12)
        col = QVBoxLayout(); col.setSpacing(1)
        t = QLabel(title)
        h = self.hint = QLabel(hint); h.setObjectName("hint")
        for w in (t, h):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        col.addWidget(t); col.addWidget(h)
        lay.addLayout(col, 1); lay.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

    def show_hint(self, on):
        self.hint.setText(self.hint_on if on else self.hint_off)

    def set_value(self, on):
        self.toggle.set_value(on)
        self.show_hint(on)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.toggle.click()


class StackRow(QFrame):
    """One pinned stack: badge (the colour, texture and lettering of its taskbar icon), name, path. Click opens its folder;
    the palette button customises the icon, the bin removes the stack."""
    def __init__(self, folder, on_remove=None, on_customize=None):
        super().__init__()
        self.setObjectName("stackrow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder = folder
        smart = smart_spec(folder) is not None
        name = os.path.basename(folder.rstrip("\\/")) or folder
        lay = QHBoxLayout(self); lay.setContentsMargins(10, 8, 12, 8); lay.setSpacing(12)
        badge = QLabel(); badge.setFixedSize(34, 34)
        pm = QPixmap.fromImage(iconstyle.badge_image(name, folder_id(folder), stack_style(folder_id(folder)), 68))
        pm.setDevicePixelRatio(2.0)
        badge.setPixmap(pm)
        col = QVBoxLayout(); col.setSpacing(0)
        t = QLabel(name)
        shown = real_folder(folder) if smart else folder
        h = QLabel(("Smart stack · from " if smart else "") + shown)
        h.setObjectName("hint")
        h.setText(h.fontMetrics().elidedText(h.text(), Qt.TextElideMode.ElideMiddle, 420))
        h.setToolTip(folder)
        col.addWidget(t); col.addWidget(h)
        go = QLabel("Open ↗"); go.setObjectName("hint")
        lay.addWidget(badge); lay.addLayout(col, 1); lay.addWidget(go)
        if on_customize is not None:
            cb = QToolButton(); cb.setObjectName("cstack"); cb.setToolTip("Customize this stack's icon")
            cb.setIcon(QIcon(palette_pixmap(16, QColor(150, 200, 235), dpr=2.0))); cb.setIconSize(QSize(16, 16))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.clicked.connect(lambda *_: on_customize(folder))
            lay.addWidget(cb)
        if on_remove is not None:
            rm = QToolButton(); rm.setObjectName("rmstack"); rm.setToolTip("Remove this stack from Foldy")
            rm.setIcon(QIcon(trash_pixmap(16, QColor(255, 140, 152), dpr=2.0))); rm.setIconSize(QSize(16, 16))
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.clicked.connect(lambda *_: on_remove(folder))
            lay.addWidget(rm)
        for w in (badge, t, h, go):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            open_path(real_folder(self.folder))


class SettingsWindow(QWidget):
    """Sidebar + pages. Fixed size, minimizable."""
    def __init__(self, hub):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint |
                         Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.hub, self.update_info = hub, None
        self.setWindowTitle("Foldy Settings")
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(SIDEBAR_QSS)
        self.setFixedSize(820, 600)
        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # ---------------------------------------------------------------- sidebar
        side = QFrame(); side.setObjectName("side"); side.setFixedWidth(210)
        sl = QVBoxLayout(side); sl.setContentsMargins(0, 18, 0, 14); sl.setSpacing(0)
        head = QHBoxLayout(); head.setContentsMargins(18, 0, 14, 0); head.setSpacing(10)
        logo = QLabel(); logo.setFixedSize(38, 38)
        logo.setPixmap(QPixmap(asset("foldy.png")).scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation))
        titles = QVBoxLayout(); titles.setSpacing(0)
        t = QLabel("Foldy"); t.setObjectName("title")
        v = QLabel(f"v{VERSION}"); v.setObjectName("hint")
        titles.addWidget(t); titles.addWidget(v)
        head.addWidget(logo); head.addLayout(titles, 1)
        sl.addLayout(head); sl.addSpacing(16)
        self.pages, self.group, self.nav = QStackedWidget(), QButtonGroup(self), []
        for n, (key, label, _sub) in enumerate(PAGES):
            b = QPushButton(label); b.setObjectName("nav"); b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b, n); self.nav.append(b); sl.addWidget(b)
        self.group.idClicked.connect(self.go)
        sl.addStretch(1)
        self.btn_update = QPushButton(" Update"); self.btn_update.setObjectName("update")
        self.btn_update.setIcon(QIcon(update_pixmap(16, QColor(6, 34, 46)))); self.btn_update.setIconSize(QSize(16, 16))
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.clicked.connect(lambda *_: hub.begin_update())
        self.btn_update.hide()
        wrap = QVBoxLayout(); wrap.setContentsMargins(14, 0, 14, 0); wrap.setSpacing(8)
        self.status = QLabel(); self.status.setObjectName("hint")        # the credit; update / pin messages replace it for a few seconds
        self.status.setWordWrap(True); self.status.setOpenExternalLinks(True)
        self.status_timer = QTimer(self, singleShot=True, interval=9000)
        self.status_timer.timeout.connect(self.show_credit)
        self.show_credit()
        wrap.addWidget(self.btn_update); wrap.addWidget(self.status)
        sl.addLayout(wrap)
        outer.addWidget(side)

        # ---------------------------------------------------------------- content
        body = QVBoxLayout(); body.setContentsMargins(26, 22, 26, 16); body.setSpacing(0)
        self.title, self.subtitle = QLabel(), QLabel()
        self.title.setObjectName("page"); self.subtitle.setObjectName("sub")
        body.addWidget(self.title); body.addWidget(self.subtitle); body.addSpacing(14)
        self.build_appearance(); self.build_behaviour(); self.build_features(); self.build_stacks(); self.build_about()
        body.addWidget(self.pages, 1)
        foot = QHBoxLayout(); foot.setContentsMargins(0, 12, 0, 0); foot.setSpacing(8)
        prev = QPushButton("Preview fan"); prev.setObjectName("accent"); prev.clicked.connect(lambda *_: hub.preview())
        prev.setCursor(Qt.CursorShape.PointingHandCursor)
        hint = QLabel("Changes apply instantly."); hint.setObjectName("hint")
        reset = QPushButton("Reset all"); reset.clicked.connect(self.reset)
        foot.addWidget(prev); foot.addWidget(hint); foot.addStretch(); foot.addWidget(reset)
        body.addLayout(foot)
        outer.addLayout(body, 1)
        self.nav[0].setChecked(True)
        self.go(0)
        self.sync()

    # ---------------------------------------------------------------- helpers
    def go(self, n):
        self.pages.setCurrentIndex(n)
        self.title.setText(PAGES[n][1]); self.subtitle.setText(PAGES[n][2])
        if PAGES[n][0] == "stacks":
            self.refresh_stacks()

    def page(self):
        """A new page: (widget, layout)."""
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        self.pages.addWidget(w)
        return w, lay

    @staticmethod
    def card():
        f = QFrame(); f.setObjectName("card")
        lay = QVBoxLayout(f); lay.setContentsMargins(18, 14, 18, 14); lay.setSpacing(10)
        return f, lay

    @staticmethod
    def sep():
        s = QFrame(); s.setObjectName("sep"); s.setFrameShape(QFrame.Shape.HLine)
        return s

    @staticmethod
    def note_label():
        n = QLabel(); n.setObjectName("note")
        return n

    def chooser(self, lay, title, hint, seg):
        row = QHBoxLayout(); row.setSpacing(12)
        col = QVBoxLayout(); col.setSpacing(1)
        col.addWidget(QLabel(title)); h = QLabel(hint); h.setObjectName("hint"); col.addWidget(h)
        row.addLayout(col, 1); row.addWidget(seg)
        lay.addLayout(row)

    def on_set(self, key, value):
        if S.get(key) != value:
            S[key] = value
            self.hub.settings_changed()

    # ---------------------------------------------------------------- pages
    def build_appearance(self):
        _, lay = self.page()
        card, cl = self.card()
        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(12)
        self.sliders, self.vals, self.resets = {}, {}, {}
        for r, (key, label, hint, lo, hi, scale, fmt) in enumerate(SLIDERS):
            col = QVBoxLayout(); col.setSpacing(0)
            col.addWidget(QLabel(label)); h = QLabel(hint); h.setObjectName("hint"); col.addWidget(h)
            sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(lo, hi); sl.setMinimumWidth(170)
            val = QLabel(); val.setObjectName("val"); val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rst = QToolButton(); rst.setObjectName("rst"); rst.setText("↺"); rst.setToolTip("Reset to default")
            rst.setCursor(Qt.CursorShape.PointingHandCursor)
            rst.clicked.connect(lambda _=False, k=key, w=sl, sc=scale: w.setValue(int(round(DEFAULTS[k] * sc))))
            sl.valueChanged.connect(lambda v, k=key, sc=scale, fm=fmt, vl=val: self.on_slider(k, v, sc, fm, vl))
            grid.addLayout(col, r, 0); grid.addWidget(sl, r, 1); grid.addWidget(val, r, 2); grid.addWidget(rst, r, 3)
            self.sliders[key], self.vals[key], self.resets[key] = sl, val, rst
        grid.setColumnStretch(1, 1)
        cl.addLayout(grid)
        lay.addWidget(card)
        self.r_labels = ToggleRow("Always show names", "Names shown beside every icon",
                                  lambda v: self.on_set("labels", v), "Names appear on hover only")
        card2, c2 = self.card(); c2.addWidget(self.r_labels)
        lay.addWidget(card2)
        lay.addStretch(1)

    def on_slider(self, key, v, scale, fmt, label):
        label.setText(fmt(v))
        self.resets[key].setEnabled(v != int(round(DEFAULTS[key] * scale)))
        self.on_set(key, v / scale if scale != 1 else v)

    def build_behaviour(self):
        _, lay = self.page()
        card, cl = self.card()
        self.sort = Segmented(SORTS)
        self.sort.changed.connect(lambda k: (self.on_set("sort", k), self.sort_note.setText(SORT_NOTES[k])))
        self.chooser(cl, "Sort by", "Order of the items in every fan", self.sort)
        self.sort_note = self.note_label(); cl.addWidget(self.sort_note)
        cl.addWidget(self.sep())
        self.drop = Segmented(DROPS)
        self.drop.changed.connect(lambda k: (self.on_set("dropmode", k), self.drop_note.setText(DROP_NOTES[k])))
        self.chooser(cl, "Files dropped on a button", "Onto a pinned button · Ctrl copies, Shift moves", self.drop)
        self.drop_note = self.note_label(); cl.addWidget(self.drop_note)
        lay.addWidget(card)
        card, cl = self.card()
        self.r_natural = ToggleRow("Natural scrolling", "Content follows your fingers",
                                   lambda v: self.on_set("natural", v), "Standard wheel direction")
        self.r_sub = ToggleRow("Folders inside folders", "Open sub-folders in the fan, with a back button",
                               lambda v: self.on_set("subfolders", v), "Folders open in Explorer instead")
        cl.addWidget(self.r_natural); cl.addWidget(self.sep()); cl.addWidget(self.r_sub)
        lay.addWidget(card)
        lay.addStretch(1)

    def build_features(self):
        _, lay = self.page()
        card, cl = self.card()
        self.r_thumbs = ToggleRow("Real thumbnails", "Pictures, videos and PDFs show a preview",
                                  lambda v: self.on_set("thumbs", v), "Every file shows its plain icon")
        self.r_type = ToggleRow("Type to filter", "Start typing in an open fan to filter it",
                                lambda v: self.on_set("typefilter", v), "Typing in an open fan does nothing")
        cl.addWidget(self.r_thumbs); cl.addWidget(self.sep()); cl.addWidget(self.r_type)
        lay.addWidget(card)
        card, cl = self.card()
        k = QLabel("KEYBOARD AND MOUSE"); k.setObjectName("sec"); cl.addWidget(k)
        grid = QGridLayout(); grid.setHorizontalSpacing(16); grid.setVerticalSpacing(5)
        for r, (key, what) in enumerate(KEYS):
            a = QLabel(key); a.setObjectName("keycap")
            b = QLabel(what); b.setObjectName("hint2")
            grid.addWidget(a, r, 0, alignment=Qt.AlignmentFlag.AlignLeft); grid.addWidget(b, r, 1)
        grid.setColumnStretch(1, 1)
        cl.addLayout(grid)
        lay.addWidget(card)
        lay.addStretch(1)

    def build_stacks(self):
        _, lay = self.page()
        bar = QHBoxLayout(); bar.setSpacing(8)
        add = QPushButton("Add folder…"); add.setObjectName("accent")
        add.clicked.connect(lambda *_: self.hub.add_folder())
        smart = QPushButton("Smart stack…"); smart.clicked.connect(lambda *_: self.hub.add_smart())
        smart.setToolTip("A stack made from a rule, like “Newest 20 downloads” or “Recent files”")
        shortcuts = QPushButton("Shortcuts folder"); shortcuts.setObjectName("ghost")
        shortcuts.clicked.connect(lambda *_: open_path(data_dir()))
        for b in (add, smart, shortcuts):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(add); bar.addWidget(smart); bar.addStretch(); bar.addWidget(shortcuts)
        lay.addLayout(bar)
        self.stack_area = QScrollArea(); self.stack_area.setWidgetResizable(True); self.stack_area.setFrameShape(QFrame.Shape.NoFrame)
        self.stack_host = QWidget(); self.stack_lay = QVBoxLayout(self.stack_host)
        self.stack_lay.setContentsMargins(0, 0, 4, 0); self.stack_lay.setSpacing(8)
        self.stack_area.setWidget(self.stack_host)
        lay.addWidget(self.stack_area, 1)

    def refresh_stacks(self):
        """List the pinned stacks (called whenever the page opens or a stack is added)."""
        while self.stack_lay.count():
            it = self.stack_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        folders = sorted(set(self.hub._stacks), key=lambda f: os.path.basename(f.rstrip("\\/")).lower())
        if not folders:
            n = QLabel("No stacks yet. Add a folder, or make a smart stack, and it gets its own taskbar button.")
            n.setObjectName("hint"); n.setWordWrap(True)
            self.stack_lay.addWidget(n)
        for f in folders:
            self.stack_lay.addWidget(StackRow(f, self.confirm_remove, self.customize))
        self.stack_lay.addStretch(1)

    def customize(self, folder):
        """Open the icon editor for a stack (one editor at a time)."""
        w = getattr(self, "icon_win", None)
        if w is not None:
            w.close(); w.deleteLater()
        self.icon_win = IconEditor(self.hub, folder, self)
        self.icon_win.show(); self.icon_win.raise_(); self.icon_win.activateWindow()

    def confirm_remove(self, folder):
        name = os.path.basename(folder.rstrip("\\/")) or folder
        smart = smart_spec(folder) is not None
        box = QMessageBox(self)
        box.setWindowTitle("Remove stack")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Remove “{name}” from Foldy?")
        box.setInformativeText("Its taskbar button, shortcut and icon are deleted" + (" together with the smart stack's rule" if smart else "") +
                               ". " + ("" if smart else "Your folder and the files in it are not touched. ") +
                               "Windows needs to restart Explorer for a moment to drop the button.")
        rm = box.addButton("Remove", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is rm:
            self.hub.remove_stack(folder)

    def build_about(self):
        _, lay = self.page()
        card, cl = self.card()
        self.r_auto = ToggleRow("Start with Windows", "Keeps your taskbar buttons instant", set_autostart,
                                "Starts at your first click (slower)")
        self.r_update = ToggleRow("Update automatically", "Asks you first when a new version is out",
                                  lambda v: self.on_set("autoupdate", v), "Never checks by itself")
        cl.addWidget(self.r_auto); cl.addWidget(self.sep()); cl.addWidget(self.r_update)
        lay.addWidget(card)
        card, cl = self.card()
        row = QHBoxLayout(); row.setSpacing(8)
        check = QPushButton("Check for updates"); check.setObjectName("ghost")
        check.clicked.connect(lambda *_: self.hub.check_updates(manual=True))
        diag = QPushButton("Copy diagnostics"); diag.setObjectName("ghost")
        diag.clicked.connect(lambda *_: self.hub.copy_diagnostics())
        fb = QPushButton("Send feedback"); fb.setObjectName("ghost")
        fb.setToolTip("Request a feature, report an issue or ask a question")
        fb.clicked.connect(lambda *_: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))
        for b in (check, diag, fb):
            b.setCursor(Qt.CursorShape.PointingHandCursor); row.addWidget(b)
        row.addStretch()
        cl.addLayout(row)
        by = QLabel(f'Foldy v{VERSION} · made by <a style="color:#4cc9ff;text-decoration:none" href="{GITHUB}">{AUTHOR}</a> · MIT licence')
        by.setObjectName("hint"); by.setOpenExternalLinks(True)
        cl.addWidget(by)
        lay.addWidget(card)
        un = QPushButton(" Uninstall Foldy…"); un.setObjectName("danger")
        un.setIcon(QIcon(trash_pixmap(16, QColor(255, 140, 152), dpr=2.0))); un.setIconSize(QSize(16, 16))
        un.setCursor(Qt.CursorShape.PointingHandCursor)
        un.clicked.connect(lambda *_: self.hub.open_uninstall())
        urow = QHBoxLayout(); urow.addWidget(un); urow.addStretch()
        lay.addLayout(urow)
        lay.addStretch(1)

    # ---------------------------------------------------------------- state
    def show_credit(self):
        self.status.setText(f'by <a style="color:#4cc9ff;text-decoration:none" href="{GITHUB}">{AUTHOR}</a>'
                            f' · <a style="color:#4cc9ff;text-decoration:none" href="{FEEDBACK_URL}">Feedback</a>')

    def set_status(self, text):
        self.status.setText(html.escape(text))                      # (the sidebar is not a fixed-size layout: wrapping just works)
        self.status_timer.start()

    def sync(self):
        """Push the current settings into the widgets without triggering change handlers."""
        for key, label, hint, lo, hi, scale, fmt in SLIDERS:
            sl = self.sliders[key]
            sl.blockSignals(True); sl.setValue(int(round(S[key] * scale))); sl.blockSignals(False)
            self.vals[key].setText(fmt(sl.value()))
            self.resets[key].setEnabled(sl.value() != int(round(DEFAULTS[key] * scale)))
        self.sort.set_value(S["sort"], animate=False); self.sort_note.setText(SORT_NOTES[S["sort"]])
        self.drop.set_value(S["dropmode"], animate=False); self.drop_note.setText(DROP_NOTES[S["dropmode"]])
        for row, v in ((self.r_labels, S["labels"]), (self.r_natural, S["natural"]), (self.r_sub, S["subfolders"]),
                       (self.r_auto, autostart_enabled()), (self.r_update, S["autoupdate"]),
                       (self.r_thumbs, S["thumbs"]), (self.r_type, S["typefilter"])):
            row.set_value(v)

    def set_update(self, info):
        """Show (or hide) the green update button at the bottom of the sidebar."""
        self.update_info = info
        b = self.btn_update
        if info is None:
            b.hide()
            return
        b.setText(f" Update to v{info['version']}")
        b.setToolTip(f"Download and install Foldy v{info['version']} (you have v{VERSION})")
        b.show()

    def reset(self):
        S.update(DEFAULTS)
        self.sync()
        self.hub.settings_changed()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
        if self.pages.currentIndex() == 3:
            self.refresh_stacks()
