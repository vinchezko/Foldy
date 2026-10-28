"""Hand-painted controls for the settings window: an animated switch and a sliding segmented control."""
from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractButton, QWidget
from .util import clamp, mix


ACCENT, ACCENT2 = (76, 201, 255), (128, 140, 255)          # the accent runs from cyan to periwinkle


class Toggle(QAbstractButton):
    """A switch: the knob glides across (with a hint of overshoot), the track fades from grey to the accent gradient,
    a soft glow blooms around it and a tick draws itself on the knob. Use set_value() to change it without animating."""
    W, H, PAD = 42, 24, 4

    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedSize(self.W + 2 * self.PAD, self.H + 2 * self.PAD)
        self._pos = 0.0
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.1)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(240)
        self.anim.setEasingCurve(ease)
        self.anim.valueChanged.connect(self._moved)
        self.toggled.connect(self._animate)
        if checked:
            self.set_value(True)

    def sizeHint(self):
        return QSize(self.W + 2 * self.PAD, self.H + 2 * self.PAD)

    def _animate(self, on):
        self.anim.stop()
        self.anim.setStartValue(float(self._pos))
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def _moved(self, v):
        self._pos = float(v)
        self.update()

    def set_value(self, on):
        """Set the state silently (no signal, no animation)."""
        self.blockSignals(True)
        self.setChecked(bool(on))
        self.blockSignals(False)
        self.anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t, pad = clamp(self._pos, 0.0, 1.0), self.PAD
        track = QRectF(pad, pad, self.W, self.H)
        r = self.H / 2
        p.setPen(Qt.PenStyle.NoPen)
        if t > 0.01:                                                    # glow
            for k, a in ((4, 22), (2, 34)):
                p.setBrush(QColor(ACCENT[0], ACCENT[1], ACCENT[2], int(a * t * (1.25 if self.underMouse() else 1.0))))
                p.drawRoundedRect(track.adjusted(-k, -k, k, k), r + k, r + k)
        g = QLinearGradient(track.left(), 0, track.right(), 0)
        hov = 10 if self.underMouse() else 0
        g.setColorAt(0, mix((58 + hov, 61 + hov, 72 + hov), ACCENT, t))
        g.setColorAt(1, mix((58 + hov, 61 + hov, 72 + hov), ACCENT2, t))
        p.setBrush(g)
        p.drawRoundedRect(track, r, r)
        p.setBrush(Qt.BrushStyle.NoBrush)                               # thin inner edge for depth
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

        d = self.H - 6.0
        kx = track.left() + 3 + (self.W - 6 - d) * self._pos            # may overshoot a hair at the end of the glide
        knob = QRectF(kx, track.top() + 3, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(knob.translated(0, 1.4))
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(knob)
        if t > 0.35:                                                    # the tick draws itself in as the switch turns on
            k = (t - 0.35) / 0.65
            c = knob.center()
            path = QPainterPath()
            path.moveTo(c.x() - 3.6, c.y() + 0.2); path.lineTo(c.x() - 1.0, c.y() + 2.9); path.lineTo(c.x() + 3.8, c.y() - 2.7)
            pen = QPen(QColor(30, 140, 220, int(255 * k)), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.setClipRect(QRectF(c.x() - 6, c.y() - 6, 12 * (0.25 + 0.75 * k), 12))      # wipe left-to-right
            p.drawPath(path)
            p.setClipping(False)
        if self.hasFocus():
            p.setPen(QPen(QColor(255, 255, 255, 150), 1.4)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(track.adjusted(-2.5, -2.5, 2.5, 2.5), r + 2.5, r + 2.5)
        p.end()


class Segmented(QWidget):
    """A row of options with one sliding highlight. A flat replacement for a drop-down: nothing to open, nothing to clip."""
    changed = pyqtSignal(str)

    def __init__(self, options):
        super().__init__()
        self.options = list(options)                                    # [(key, text), ...]
        self.idx, self._x, self.hover = 0, 0.0, -1
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        self.anim.valueChanged.connect(self._moved)

    def seg_w(self):
        fm = self.fontMetrics()
        return max(fm.horizontalAdvance(t) for _, t in self.options) + 28

    def sizeHint(self):
        return QSize(self.seg_w() * len(self.options) + 8, 30)

    def value(self):
        return self.options[self.idx][0]

    def _moved(self, v):
        self._x = float(v)
        self.update()

    def set_value(self, key, animate=True):
        i = next((n for n, (k, _) in enumerate(self.options) if k == key), 0)
        self.anim.stop()
        if animate and i != self.idx:
            self.anim.setStartValue(float(self._x)); self.anim.setEndValue(float(i)); self.anim.start()
        else:
            self._x = float(i)
        self.idx = i
        self.update()

    def _index_at(self, x):
        return int(clamp((x - 4) // self.seg_w(), 0, len(self.options) - 1))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pick(self._index_at(e.position().x()))

    def _pick(self, i):
        if i != self.idx:
            self.set_value(self.options[i][0])
            self.changed.emit(self.options[i][0])

    def mouseMoveEvent(self, e):
        h = self._index_at(e.position().x())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._pick(max(0, self.idx - 1))
        elif e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._pick(min(len(self.options) - 1, self.idx + 1))
        else:
            super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w, h, sw = self.width(), self.height(), self.seg_w()
        body = QRectF(0.5, 0.5, w - 1, h - 1)
        p.setBrush(QColor(33, 35, 42)); p.setPen(QPen(QColor(61, 64, 74), 1))
        p.drawRoundedRect(body, h / 2 - 0.5, h / 2 - 0.5)
        pill = QRectF(4 + self._x * sw, 3.5, sw, h - 7)
        g = QLinearGradient(pill.left(), 0, pill.right(), 0)
        g.setColorAt(0, QColor(*ACCENT)); g.setColorAt(1, QColor(*ACCENT2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT[0], ACCENT[1], ACCENT[2], 40)); p.drawRoundedRect(pill.adjusted(-2, -2, 2, 2), pill.height() / 2 + 2, pill.height() / 2 + 2)
        p.setBrush(g); p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        f = self.font(); p.setFont(f)
        for i, (_, text) in enumerate(self.options):
            k = max(0.0, 1.0 - abs(i - self._x))                       # 1 under the pill, 0 away from it
            base = (205, 210, 220) if i == self.hover else (150, 156, 169)
            p.setPen(mix(base, (8, 28, 38), k))
            p.drawText(QRectF(4 + i * sw, 0, sw, h), int(Qt.AlignmentFlag.AlignCenter), text)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 120), 1.2))
            p.drawRoundedRect(body.adjusted(-1.5, -1.5, 1.5, 1.5), h / 2 + 1, h / 2 + 1)
        p.end()


def update_pixmap(size, color, dpr=2.0):
    """A circled up-arrow: the 'an update is waiting' icon."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, size * 0.09)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)
    p.drawEllipse(QRectF(0.08 * s, 0.08 * s, 0.84 * s, 0.84 * s))
    p.drawLine(QPointF(0.5 * s, 0.70 * s), QPointF(0.5 * s, 0.30 * s))
    p.drawLine(QPointF(0.5 * s, 0.30 * s), QPointF(0.34 * s, 0.46 * s))
    p.drawLine(QPointF(0.5 * s, 0.30 * s), QPointF(0.66 * s, 0.46 * s))
    p.end()
    return pm
