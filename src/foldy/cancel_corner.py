"""The cancel ✕: a small button in the top-left corner of the screen (not in the fan) that appears while a file is being
carried out of a fan. Drop the file on it and the move is cancelled. It grows into a pill that explains itself."""
import math, time
from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRegion
from PyQt6.QtWidgets import QApplication, QWidget
from .render import ui_font
from .settings import S, log
from .util import clamp
from .winutil import key_down, pin_topmost

W, H = 336, 90                                      # window size (the pill grows inside it)
MARGIN = 18                                         # distance from the screen corner
OPEN_SECONDS = 0.6                                  # how long the grow animation takes at normal speed
FADE_SECONDS = 0.28


def ease_out_back(t):
    t = clamp(t, 0.0, 1.0)
    c1 = 1.5
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


class CancelCorner(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.want, self.hover, self.wait = False, False, False      # wait: asked to hide, but the mouse button is still down
        self.k, self.a = 0.0, 0.0                   # grow progress (0..1) and visibility (0..1)
        self.last = time.perf_counter()
        self.timer = QTimer(self, interval=15)
        self.timer.timeout.connect(self.step)
        self.winId()

    # ---- control (called by the fan)
    def activate(self, on):
        self.want = on
        self.wait = not on and key_down(0x01)                      # a file may still be on the cursor: stay until it is let go
        if on:
            g = QApplication.primaryScreen().geometry()
            self.setGeometry(g.x() + MARGIN, g.y() + MARGIN, W, H)
            self.apply_mask()
            if not self.isVisible():
                self.show()
                pin_topmost(self)
        else:
            self.hover = False
        self.last = time.perf_counter()
        self.timer.start()

    def rect(self):
        e = ease_out_back(self.k)
        return QRectF(0, 0, 52 + 264 * e, 52 + 22 * clamp(e, 0.0, 1.0))

    def apply_mask(self):
        self.setMask(QRegion(self.rect().toAlignedRect().adjusted(0, 0, 4, 4)))      # only the pill itself takes (and blocks) the mouse

    def step(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        spd = max(S["speed"], 0.1)
        if self.wait and not key_down(0x01):
            self.wait = False
        keep = self.want or self.wait
        tk = 1.0 if (keep and self.hover) else 0.0
        ta = 1.0 if keep else 0.0
        self.k += clamp(tk - self.k, -dt * spd / OPEN_SECONDS, dt * spd / OPEN_SECONDS)     # constant-speed tween, eased when drawn
        self.a += clamp(ta - self.a, -dt / FADE_SECONDS, dt / FADE_SECONDS)
        self.apply_mask()
        self.update()
        if self.a <= 0.0 and not keep:
            self.timer.stop()
            self.hide()
        elif self.k == tk and self.a == ta and not keep:
            self.timer.stop()

    # ---- the file is carried over the ✕ (it is a real drop target while the fan's drag is a shell drag)
    def dragEnterEvent(self, e):
        self.hover = True
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        self.timer.start()

    def dragMoveEvent(self, e):
        self.hover = True
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()

    def dragLeaveEvent(self, e):
        self.hover = False
        self.timer.start()

    def dropEvent(self, e):
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()                                  # accepted but nothing is done with it: that IS the cancel
        self.hover = False
        log("cancel corner: move cancelled")
        self.timer.start()

    # ---- drawing
    def paintEvent(self, e):
        if self.a <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        r, k = self.rect(), clamp(ease_out_back(self.k), 0.0, 1.0)
        p.setOpacity(self.a)
        p.fillRect(r.adjusted(0, 0, 0, 0), QColor(0, 0, 0, 1))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(5):                                                  # soft shadow
            p.setBrush(QColor(0, 0, 0, 16))
            p.drawRoundedRect(r.adjusted(-i, -i + 2, i, i + 2), r.height() / 2 + i, r.height() / 2 + i)
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, QColor(int(66 + 96 * k), 36, 42, 246)); g.setColorAt(1, QColor(int(42 + 70 * k), 24, 30, 250))
        rad = r.height() / 2 * (1 - k) + 18 * k
        p.setBrush(g); p.setPen(QPen(QColor(255, 128, 128, int(130 + 120 * k)), 1.6))
        p.drawRoundedRect(r.adjusted(.8, .8, -.8, -.8), rad, rad)
        cx, cy = 26.0, r.height() / 2                                       # the ✕ turns a quarter as the pill opens
        p.save(); p.translate(cx, cy); p.rotate(90 * k)
        p.setPen(QPen(QColor(255, 255, 255, 245), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(-7, -7), QPointF(7, 7)); p.drawLine(QPointF(-7, 7), QPointF(7, -7))
        p.restore()
        if k > 0.5:                                                         # the explanation appears once there is room
            p.setOpacity(self.a * clamp((k - 0.5) / 0.4, 0.0, 1.0))
            p.setClipRect(QRectF(54, 0, r.width() - 60, r.height()))
            tf = QFont(ui_font(14)); tf.setBold(True)
            p.setFont(tf); p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(60, 10, r.width() - 70, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Cancel move")
            p.setFont(ui_font(11)); p.setPen(QColor(255, 255, 255, 215))
            p.drawText(QRectF(60, 36, r.width() - 70, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "Drop here: the file stays where it is")
            p.setClipping(False)
        p.end()


_corner = None


def corner():
    global _corner
    if _corner is None:
        _corner = CancelCorner()
    return _corner
