"""The right-click menu of a fan item, drawn by hand so it matches the fan: frosted glass, a header with the item's own
picture, line icons, key hints and a small pop-in. Open, Open with…, Show in Explorer, Copy path."""
import ctypes, os, subprocess, sys, time
from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget
from .render import ui_font
from .settings import log
from .winutil import open_path


def show_in_explorer(path):
    """Open the containing folder with the item selected."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            open_path(os.path.dirname(path))
    except Exception as ex:
        log(f"show in explorer failed: {ex!r}")


def open_with(path):
    """Windows' own 'How do you want to open this?' list (every app that can open the file)."""
    try:
        r = ctypes.windll.shell32.ShellExecuteW(None, "openas", os.path.normpath(path), None, None, 1)
        if r <= 32:
            log(f"open with: ShellExecute returned {r}")
    except Exception as ex:
        log(f"open with failed: {ex!r}")


def copy_path(path):
    QApplication.clipboard().setText(os.path.normpath(path))


def describe(path, is_dir):
    """'PDF · 2.3 MB · Today 14:05' under the name."""
    try:
        st = os.stat(path)
    except OSError:
        return ""
    when, now = time.localtime(st.st_mtime), time.localtime()
    if when[:3] == now[:3]:
        day = "Today " + time.strftime("%H:%M", when)
    elif time.localtime(st.st_mtime + 86400)[:3] == now[:3]:
        day = "Yesterday " + time.strftime("%H:%M", when)
    else:
        day = time.strftime("%d %b %Y", when)
    if is_dir:
        return f"Folder · {day}"
    kind = os.path.splitext(path)[1].lstrip(".").upper() or "File"
    n, units, u = float(st.st_size), ["B", "KB", "MB", "GB", "TB"], 0
    while n >= 1024 and u < len(units) - 1:
        n /= 1024; u += 1
    size = f"{int(n)} {units[u]}" if u == 0 else f"{n:.1f} {units[u]}"
    return f"{kind} · {size} · {day}"


def glyph(p, kind, r, color):
    """Line icons, drawn at the size they are needed (no image files)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.7); pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
    x, y, u = r.x(), r.y(), r.width() / 16.0
    P = lambda a, b: QPointF(x + a * u, y + b * u)
    if kind == "open":                                           # a box with an arrow leaving through its corner
        path = QPainterPath()
        path.moveTo(P(7, 3)); path.lineTo(P(4, 3)); path.quadTo(P(2, 3), P(2, 5)); path.lineTo(P(2, 12))
        path.quadTo(P(2, 14), P(4, 14)); path.lineTo(P(11, 14)); path.quadTo(P(13, 14), P(13, 12)); path.lineTo(P(13, 9))
        p.drawPath(path)
        p.drawLine(P(9, 2), P(14, 2)); p.drawLine(P(14, 2), P(14, 7)); p.drawLine(P(14, 2), P(7, 9))
    elif kind == "with":                                         # four little tiles: 'choose an app'
        for dx in (2.5, 9):
            for dy in (2.5, 9):
                p.drawRoundedRect(QRectF(x + dx * u, y + dy * u, 4.5 * u, 4.5 * u), 1.4 * u, 1.4 * u)
    elif kind == "show":                                         # a folder with a magnifier
        base = QPainterPath()
        base.moveTo(P(1.5, 5)); base.lineTo(P(1.5, 12)); base.quadTo(P(1.5, 13.5), P(3, 13.5)); base.lineTo(P(8, 13.5))
        p.drawPath(base)
        top = QPainterPath()
        top.moveTo(P(1.5, 5)); top.lineTo(P(1.5, 3.5)); top.quadTo(P(1.5, 2.5), P(2.5, 2.5)); top.lineTo(P(5.5, 2.5))
        top.lineTo(P(7, 4)); top.lineTo(P(12, 4)); top.quadTo(P(13.5, 4), P(13.5, 5.5)); top.lineTo(P(13.5, 6))
        p.drawPath(top)
        p.drawEllipse(P(10.5, 10), 2.7 * u, 2.7 * u)
        p.drawLine(P(12.5, 12), P(14.5, 14))
    elif kind == "copy":                                         # two sheets
        p.drawRoundedRect(QRectF(x + 5.5 * u, y + 1.5 * u, 8.5 * u, 9.5 * u), 2 * u, 2 * u)
        path = QPainterPath()
        path.moveTo(P(4, 5)); path.quadTo(P(2, 5), P(2, 7)); path.lineTo(P(2, 13)); path.quadTo(P(2, 14.5), P(3.5, 14.5))
        path.lineTo(P(9, 14.5))
        path.quadTo(P(10.5, 14.5), P(10.5, 13))
        p.drawPath(path)
    p.restore()


class ItemMenu(QWidget):
    """Frosted-glass popup. `chosen(key)` fires when an action ran; `closed` whenever it goes away (either way)."""
    chosen = pyqtSignal(str)
    closed = pyqtSignal()

    M, W, ROW, HEAD = 14, 262, 34, 62                           # shadow margin, content width, row height, header height
    ACTIONS = [("open", "Open", "Enter"), ("with", "Open with…", ""), None,
               ("show", "Show in Explorer", "Shift+Enter"), ("copy", "Copy path", "")]

    def __init__(self, parent, path, is_dir, icon=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.path, self.is_dir, self.icon = path, is_dir, icon
        self.name = os.path.basename(path.rstrip("\\/")) or path
        self.sub = describe(path, is_dir)
        self.rows, self.items = [], []                            # real actions: (key, label, hint, rect); layout incl. separators
        y = self.M + self.HEAD + 6
        for a in self.ACTIONS:
            if a is None:
                self.items.append(None); y += 9
                continue
            if a[0] == "with" and is_dir:
                continue
            self.rows.append((a[0], a[1], a[2], QRectF(self.M + 6, y, self.W - 12, self.ROW)))
            self.items.append(a[0]); y += self.ROW
        self.hover = -1
        self.setFixedSize(self.W + 2 * self.M, int(y + 6 + self.M))
        self.t, self.home, self.shown_at = 0.0, QPointF(), 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(170); self.anim.setStartValue(0.0); self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        self.anim.valueChanged.connect(self._tick)

    # ---- show / hide
    def popup(self, gpos):
        scr = QGuiApplication.screenAt(gpos.toPoint() if hasattr(gpos, "toPoint") else gpos) or QGuiApplication.primaryScreen()
        a = scr.availableGeometry()
        gx, gy = int(gpos.x()), int(gpos.y())
        x, y = gx - self.M + 4, gy - self.M + 4
        if x + self.width() > a.right():
            x = gx - self.width() + self.M - 4                    # no room on the right: open to the left of the pointer
        if y + self.height() > a.bottom():
            y = gy - self.height() + self.M - 4                   # no room below: open upwards
        self.home = QPointF(max(a.left(), x), max(a.top(), y))
        self.move(int(self.home.x()), int(self.home.y() + 8))
        self.setWindowOpacity(0.0)
        self.show()
        self.shown_at = time.perf_counter()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self.anim.start()

    def _tick(self, v):
        self.t = float(v)
        self.setWindowOpacity(self.t)
        self.move(int(self.home.x()), int(self.home.y() + 8 * (1 - self.t)))

    def hideEvent(self, e):
        super().hideEvent(e)
        self.closed.emit()

    # ---- actions
    def run(self, key):
        fn = {"open": open_path, "with": open_with, "show": show_in_explorer, "copy": copy_path}[key]
        self.hide()
        try:
            fn(self.path)
        except Exception as ex:
            log(f"menu action {key} failed: {ex!r}")
        self.chosen.emit(key)

    def row_at(self, pos):
        for n, (_, _, _, r) in enumerate(self.rows):
            if r.contains(pos):
                return n
        return -1

    def mouseMoveEvent(self, e):
        n = self.row_at(e.position())
        if n != self.hover:
            self.hover = n
            self.update()
        self.setCursor(Qt.CursorShape.PointingHandCursor if n >= 0 else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or time.perf_counter() - self.shown_at < 0.12:
            return                                                # (the button that opened the menu is still going up)
        n = self.row_at(e.position())
        if n >= 0:
            self.run(self.rows[n][0])

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            return self.hide()
        if k in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self.hover = (self.hover + 1) % len(self.rows)
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            self.hover = (self.hover - 1) % len(self.rows) if self.hover >= 0 else len(self.rows) - 1
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.hover >= 0:
                return self.run(self.rows[self.hover][0])
        else:
            return super().keyPressEvent(e)
        self.update()

    # ---- painting
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing |
                         QPainter.RenderHint.SmoothPixmapTransform)
        m, W = self.M, self.W
        body = QRectF(m, m, W, self.height() - 2 * m)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(0, m - 2, 2):                              # soft shadow
            p.setBrush(QColor(0, 0, 0, int(20 * (1 - k / m) + 1)))
            p.drawRoundedRect(QRectF(m - k, m - k + 3, W + 2 * k, body.height() + 2 * k), 14 + k, 14 + k)
        g = QLinearGradient(0, body.top(), 0, body.bottom())
        g.setColorAt(0, QColor(58, 60, 70, 248)); g.setColorAt(1, QColor(30, 31, 37, 250))
        p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, 52), 1))
        p.drawRoundedRect(body.adjusted(.5, .5, -.5, -.5), 14, 14)
        # header: the item's own picture, its name and details
        ic = QRectF(m + 14, m + 12, 38, 38)
        if self.icon is not None and not self.icon.isNull():
            p.drawPixmap(ic, self.icon, QRectF(self.icon.rect()))
        tx = ic.right() + 12
        room = int(m + W - 14 - tx)
        f1 = ui_font(13); f1.setWeight(QFont.Weight.DemiBold)
        p.setFont(f1); p.setPen(QColor(246, 247, 250))
        p.drawText(QPointF(tx, m + 28), QFontMetrics(f1).elidedText(self.name, Qt.TextElideMode.ElideMiddle, room))
        f2 = ui_font(11); f2.setWeight(QFont.Weight.Normal)
        p.setFont(f2); p.setPen(QColor(150, 156, 170))
        p.drawText(QPointF(tx, m + 45), QFontMetrics(f2).elidedText(self.sub, Qt.TextElideMode.ElideRight, room))
        # separators
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(m + 14, m + self.HEAD + 3), QPointF(m + W - 14, m + self.HEAD + 3))
        y = m + self.HEAD + 6
        for it in self.items:
            if it is None:
                p.drawLine(QPointF(m + 14, y + 4.5), QPointF(m + W - 14, y + 4.5)); y += 9
            else:
                y += self.ROW
        # rows
        for n, (key, label, hint, r) in enumerate(self.rows):
            on = n == self.hover
            if on:
                hg = QLinearGradient(r.left(), 0, r.right(), 0)
                hg.setColorAt(0, QColor(76, 201, 255, 62)); hg.setColorAt(1, QColor(128, 140, 255, 46))
                p.setPen(QPen(QColor(120, 185, 255, 110), 1)); p.setBrush(hg)
                p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 9, 9)
            glyph(p, key, QRectF(r.left() + 11, r.center().y() - 8, 16, 16),
                  QColor(255, 255, 255) if on else QColor(196, 201, 214))
            p.setFont(ui_font(13)); p.setPen(QColor(255, 255, 255) if on else QColor(230, 232, 238))
            p.drawText(QPointF(r.left() + 38, r.center().y() + 4.5), label)
            if hint:
                hf = ui_font(11); hf.setWeight(QFont.Weight.Normal)
                p.setFont(hf); p.setPen(QColor(135, 141, 156))
                p.drawText(QRectF(r.left(), r.top(), r.width() - 12, r.height()),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, hint)
        p.end()


def build(parent, path, is_dir, icon=None):
    """The menu for `path` (the caller connects chosen / closed and calls popup())."""
    return ItemMenu(parent, path, is_dir, icon)
