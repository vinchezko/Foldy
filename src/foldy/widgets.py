"""Reusable widgets: trash icon, smooth progress bar, step-by-step progress window, hold-to-confirm ring button."""
import math, threading, time, traceback
from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .render import ui_font
from .settings import log
from .styles import SETTINGS_QSS
from .util import clamp, mix
from .winutil import asset, center_on_screen, dark_titlebar


def trash_pixmap(size, color, lid=0.0, dpr=1.0):
    """Trash-can icon drawn with a painter; `lid` (0..1) lifts the lid."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, size * 0.075)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)
    body = QPainterPath()
    body.moveTo(0.27 * s, 0.38 * s); body.lineTo(0.32 * s, 0.82 * s)
    body.lineTo(0.68 * s, 0.82 * s); body.lineTo(0.73 * s, 0.38 * s)
    p.drawPath(body)
    p.drawLine(QPointF(0.43 * s, 0.50 * s), QPointF(0.43 * s, 0.70 * s))
    p.drawLine(QPointF(0.57 * s, 0.50 * s), QPointF(0.57 * s, 0.70 * s))
    p.save()
    p.translate(0.25 * s, 0.31 * s); p.rotate(-26.0 * lid); p.translate(-0.25 * s, -0.31 * s)
    lid_path = QPainterPath()
    lid_path.moveTo(0.20 * s, 0.31 * s); lid_path.lineTo(0.80 * s, 0.31 * s)
    lid_path.moveTo(0.40 * s, 0.31 * s); lid_path.lineTo(0.40 * s, 0.23 * s)
    lid_path.lineTo(0.60 * s, 0.23 * s); lid_path.lineTo(0.60 * s, 0.31 * s)
    p.drawPath(lid_path)
    p.restore()
    p.end()
    return pm


class HoldButton(QWidget):
    """Press and hold: a ring draws itself around the button; the moment its end meets its start, `confirmed` fires.
    Letting go early smoothly unwinds the ring, so nothing happens by accident."""
    confirmed = pyqtSignal()
    HOLD, UNWIND = 1.5, 0.45                       # seconds to fill / to unwind

    def __init__(self):
        super().__init__()
        self.setFixedSize(140, 150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.progress = self.press = self.flash = 0.0
        self.holding = self.done = False
        self.last = 0.0
        self.timer = QTimer(self, interval=8)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)

    def begin(self):
        if not self.done:
            self.holding = True
            self.kick()

    def end(self):
        self.holding = False
        self.kick()

    def kick(self):
        if not self.timer.isActive():
            self.last = time.perf_counter()
            self.timer.start()

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        if self.done:
            self.progress = 1.0
        elif self.holding:
            self.progress = min(1.0, self.progress + dt / self.HOLD)
        else:
            self.progress = max(0.0, self.progress - dt / self.UNWIND)
        self.press += ((1.0 if self.holding else 0.0) - self.press) * (1 - math.exp(-dt * 18))
        self.flash = max(0.0, self.flash - dt * 2.5)
        if self.progress >= 1.0 and not self.done:                  # ring closed: end touched start
            self.done, self.holding, self.flash = True, False, 1.0
            self.confirmed.emit()
        self.update()
        if not self.holding and (self.done or self.progress <= 0.0) and self.flash <= 0.0 and self.press < 0.01:
            self.timer.stop()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.begin()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.end()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.isAutoRepeat():
            self.begin()

    def keyReleaseEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.isAutoRepeat():
            self.end()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.end()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        c = QPointF(self.width() / 2, 70.0)
        t, ring = self.progress, 52.0
        rect = QRectF(c.x() - ring, c.y() - ring, 2 * ring, 2 * ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 30), 6))
        p.drawEllipse(c, ring, ring)                                          # empty ring
        if t > 0.001:
            col = mix((255, 176, 92), (255, 72, 92), t)
            glow = QColor(col); glow.setAlpha(55)
            for color, width in ((glow, 16), (col, 6)):
                pen = QPen(color, width); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(rect, 90 * 16, int(-t * 360 * 16))                  # clockwise from 12 o'clock
        if self.flash > 0:
            p.setPen(QPen(QColor(255, 255, 255, int(200 * self.flash)), 6))
            p.drawEllipse(c, ring, ring)
        r = 40.0 * (1 - 0.06 * self.press)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(mix((44, 46, 54), (96, 34, 46), t))
        p.drawEllipse(c, r, r)
        pm = trash_pixmap(40, mix((235, 238, 245), (255, 150, 160), t), lid=t, dpr=self.devicePixelRatioF())
        p.drawPixmap(QPointF(c.x() - 20, c.y() - 20), pm)
        p.setPen(QColor(154, 160, 171))
        p.setFont(ui_font(12))
        text = "Uninstalling…" if self.done else "Keep holding…" if t > 0.02 else "Hold to uninstall"
        p.drawText(QRectF(0, 128, self.width(), 20), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class Bar(QWidget):
    """Smooth, eased progress bar."""
    def __init__(self, accent=(76, 201, 255)):
        super().__init__()
        self.accent, self.value, self.target = accent, 0.0, 0.0
        self.setFixedHeight(12)
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.tick)

    def set_target(self, v):
        self.target = clamp(v, 0.0, 1.0)
        if not self.timer.isActive():
            self.timer.start()

    def tick(self):
        self.value += (self.target - self.value) * 0.16
        if abs(self.target - self.value) < 0.001:
            self.value = self.target
            self.timer.stop()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 1, self.width(), self.height() - 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 24))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.value > 0.001:
            fill = QRectF(r.left(), r.top(), max(r.height(), r.width() * self.value), r.height())
            g = QLinearGradient(fill.left(), 0, fill.right(), 0)
            g.setColorAt(0, QColor(*self.accent)); g.setColorAt(1, QColor(*self.accent).lighter(135))
            p.setBrush(g)
            p.drawRoundedRect(fill, r.height() / 2, r.height() / 2)
        p.end()


class StepRunner(QObject):
    """Runs (label, weight, fn) steps on a worker thread and reports progress back to the UI thread."""
    state = pyqtSignal(int, str)                   # step index, "run" | "ok" | "fail"
    progress = pyqtSignal(float, str)              # overall 0..1, detail text
    finished = pyqtSignal(bool, str)

    def __init__(self, steps, stop_on_error=True):
        super().__init__()
        self.steps, self.stop_on_error = steps, stop_on_error

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        pc = None
        try:
            import pythoncom as pc
            pc.CoInitialize()
        except Exception:
            pc = None
        total, done, err = float(sum(w for _, w, _ in self.steps)), 0.0, ""
        for i, (label, weight, fn) in enumerate(self.steps):
            self.state.emit(i, "run")

            def report(frac, text="", _d=done, _w=weight):
                self.progress.emit((_d + _w * clamp(frac, 0.0, 1.0)) / total, text)
            try:
                fn(report)
                time.sleep(0.15)                                   # let every step be seen
                self.state.emit(i, "ok")
            except Exception as ex:
                log(f"step '{label}' failed:\n{traceback.format_exc()}")
                self.state.emit(i, "fail")
                if self.stop_on_error:
                    err = f"{label}: {ex}"
                    break
            done += weight
            self.progress.emit(done / total, "")
        if pc is not None:
            try:
                pc.CoUninitialize()
            except Exception:
                pass
        self.finished.emit(not err, err)


class StepWindow(QWidget):
    """Progress window with a smooth bar and a checklist; used for both installing and uninstalling."""
    FRAMES = "◐◓◑◒"

    def __init__(self, title, names, accent=(76, 201, 255), stop_on_error=True, done_title="Done", done_sub=""):
        super().__init__()
        self.names, self.accent, self.stop_on_error = names, accent, stop_on_error
        self.done_title, self.done_sub = done_title, done_sub
        self.running, self.cur, self.frame, self.on_done = False, -1, 0, None
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(SETTINGS_QSS)
        self.setFixedWidth(500)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(12)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(asset("foldy.png")).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation))
        titles = QVBoxLayout(); titles.setSpacing(0)
        self.title = QLabel(title); self.title.setObjectName("title")
        self.sub = QLabel("Getting ready…"); self.sub.setObjectName("sub"); self.sub.setWordWrap(True)
        titles.addWidget(self.title); titles.addWidget(self.sub)
        head.addWidget(logo); head.addSpacing(12); head.addLayout(titles, 1)
        root.addLayout(head)
        self.bar = Bar(accent)
        root.addWidget(self.bar)
        meta = QHBoxLayout()
        self.detail = QLabel(""); self.detail.setObjectName("sub")
        self.pct = QLabel("0%"); self.pct.setObjectName("val"); self.pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        meta.addWidget(self.detail, 1); meta.addWidget(self.pct)
        root.addLayout(meta)
        sep = QFrame(); sep.setObjectName("sep"); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)
        self.glyphs = []
        for n in names:
            row = QHBoxLayout()
            g = QLabel("○"); g.setFixedWidth(24); g.setStyleSheet("color:#4b4f5b;font-size:15px;")
            t = QLabel(n); t.setStyleSheet("color:#9aa0ab;")
            row.addWidget(g); row.addWidget(t, 1)
            root.addLayout(row)
            self.glyphs.append((g, t))
        self.close_btn = QPushButton("Close"); self.close_btn.hide(); self.close_btn.clicked.connect(self.close)
        root.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.spin = QTimer(self, interval=110)
        self.spin.timeout.connect(self.spin_tick)

    def begin(self, steps, on_done):
        self.on_done, self.running = on_done, True
        self.runner = StepRunner(steps, self.stop_on_error)
        self.runner.state.connect(self.set_state)
        self.runner.progress.connect(self.set_progress)
        self.runner.finished.connect(self.on_finished)
        self.spin.start()
        self.runner.start()

    def set_state(self, i, st):
        g, t = self.glyphs[i]
        if st == "run":
            self.cur = i
            g.setStyleSheet(f"color:rgb{self.accent};font-size:15px;"); t.setStyleSheet("color:#ffffff;")
            self.sub.setText(self.names[i] + "…")
        elif st == "ok":
            g.setText("✓"); g.setStyleSheet("color:#5ee08a;font-size:15px;"); t.setStyleSheet("color:#cfd3dc;")
        else:
            g.setText("✕"); g.setStyleSheet("color:#ff6b78;font-size:15px;"); t.setStyleSheet("color:#ff9aa4;")

    def set_progress(self, frac, text):
        self.bar.set_target(frac)
        self.pct.setText(f"{int(frac * 100)}%")
        if text:
            self.detail.setText(text)

    def spin_tick(self):
        if self.running and self.cur >= 0:
            g, _ = self.glyphs[self.cur]
            if g.text() not in ("✓", "✕"):
                self.frame = (self.frame + 1) % 4
                g.setText(self.FRAMES[self.frame])

    def on_finished(self, ok, msg):
        self.running = False
        self.spin.stop()
        if ok:
            self.bar.set_target(1.0); self.pct.setText("100%"); self.detail.setText("")
            self.title.setText(self.done_title); self.sub.setText(self.done_sub)
            QTimer.singleShot(1500, lambda: self.on_done and self.on_done(True))
        else:
            self.title.setText("Something went wrong")
            self.sub.setText(msg + "\nDetails: %APPDATA%\\Foldy\\foldy.log")
            self.close_btn.show()

    def closeEvent(self, e):
        if self.running:
            e.ignore()
        else:
            super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
        QTimer.singleShot(0, lambda: center_on_screen(self))
