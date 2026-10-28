"""The fan overlay: arc layout, spring animation, push-apart magnification and kinetic scrolling."""
import math, os, time
from PyQt6.QtCore import QPointF, QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QRadialGradient, QRegion
from PyQt6.QtWidgets import QApplication, QWidget
from .constants import (BASE_ICON, BASE_SP, C_CLOSE, C_OPEN, K, SCROLL_C, SCROLL_K, STAG_CLOSE, STAG_OPEN,
                        WIN_W)
from .render import Elt, entries_for
from .settings import S
from .util import clamp, smooth
from .winutil import key_down, open_path, pin_topmost, timer_resolution


class FanOverlay(QWidget):
    """Small fixed-size window just big enough for the fan. Never takes focus; clicks pass through everywhere
    except the fan itself and the clicked button (window mask). Items are laid out along a circular arc."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.entries, self.cache, self.header = [], {}, None
        self.folder, self.is_open = None, False
        self.root, self.loc, self.back = None, {}, None              # pinned folder, where it opened, the 'back' pill
        self.stack, self.nav_to, self.restore = [], None, None       # folders-in-folders: ancestors, target, scroll to restore
        self._bs = False
        self.mouse = self.hover = None
        self.bend, self.label_side, self.origin, self.start = 1, -1, QPointF(), 70.0
        self.sp, self.isz, self.R, self.cap, self.dpr = BASE_SP, BASE_ICON, 900.0, 10, 1.0
        self.scroll = self.sv = self.target = self.maxscroll = 0.0
        self.t_wheel = self.focus = 0.0
        self.bounds, self.region = QRect(), QRegion()
        self.last = self.t_open = 0.0
        self.lift, self.tb_y = 0.0, 0.0
        self.res_on = False
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self.step)
        self.poll = QTimer(self, interval=30)                       # outside-click / Esc detection (only while open)
        self.poll.timeout.connect(self.check_dismiss)
        self.winId()                                                # create the native window up-front

    # ---- build
    def build(self, folder, loc):
        scr = QApplication.primaryScreen()
        g, a, self.dpr = scr.geometry(), scr.availableGeometry(), scr.devicePixelRatio()
        d = S["density"]
        self.isz, self.sp = round(BASE_ICON * d), round(BASE_SP * d)
        bottom = g.y() + g.height()
        tb_top = loc.get("tb_top")                                  # real taskbar top edge (any scale / size / auto-hide)
        th = bottom - tb_top if tb_top is not None else bottom - (a.y() + a.height())
        if th < 20 or th > 220:                                     # auto-hidden bar / odd value: Windows 11 default size
            th = 48
        maxvis = int(S["maxvis"])
        H = int(min(g.height(), maxvis * self.sp + th * 1.5 + self.isz + 150))
        cxg = clamp(loc["cx"], g.left() + 30, g.right() - 30)
        wx = int(clamp(cxg - WIN_W / 2, g.left(), g.right() - WIN_W + 1))
        self.setGeometry(wx, bottom - H, WIN_W, H)
        self.tb_y = float(H - th)                                   # taskbar top edge in window coordinates
        cy = loc.get("cy") if loc.get("exact") else None
        cy_win = clamp((cy - (bottom - H)) if cy is not None else H - th / 2, self.tb_y + 4, H - 2)
        self.origin = QPointF(cxg - wx, cy_win)                     # centre of the clicked taskbar button
        self.start = (self.origin.y() - self.tb_y) + self.isz / 2 + 8   # first icon sits just clear of the taskbar
        self.lift = 0.0
        self.cap = int(clamp((self.origin.y() - self.start - 60) // self.sp, 1, maxvis))
        reach = self.cap * self.sp + 120
        self.R = max(2000 - 1500 * S["curve"], reach / 1.1)         # keep the arc under ~63 degrees
        ext = self.R * (1 - math.cos(reach / self.R))               # how far the top of the arc bends sideways
        if self.origin.x() + ext + 50 <= WIN_W:
            self.bend = 1
        elif self.origin.x() - ext - 300 >= 0:
            self.bend = -1
        else:
            self.bend = 1
        self.label_side = 1 if self.origin.x() < 300 else -1

        self.entries = entries_for(folder, S["sort"])
        self.maxscroll = float(max(0, len(self.entries) - self.cap))
        self.scroll = self.sv = self.target = 0.0
        self.cache = {}
        self.header = Elt("header", folder, "Open in Explorer  ↗", self.dpr)
        self.back = None
        if self.stack:                                              # inside a sub-folder: a pill that leads back up
            parent = self.stack[-1][0]
            self.back = Elt("back", parent, "◀  " + (os.path.basename(parent.rstrip("\\/")) or parent), self.dpr)
        self.ensure_cache()

        ytop = self.origin.y() - self.start - self.R * math.sin(reach / self.R) - 70
        top = int(max(0, ytop))
        xs = (self.origin.x(), self.origin.x() + self.bend * ext)
        left = int(max(0, min(xs) - 60 - (330 if self.label_side < 0 else 0)))
        right = int(min(WIN_W, max(xs) + 60 + (330 if self.label_side > 0 else 0)))
        self.bounds = QRect(left, top, right - left, H - top)
        fan = QRegion(QRect(left, top, right - left, int(self.tb_y) - top))
        self.region = fan.united(QRegion(QRect(int(self.origin.x()) - 36, int(self.tb_y), 72, int(H - self.tb_y))))
        self.setMask(self.region)                                   # everything else stays click-through

    def ensure_cache(self):
        lo = max(0, int(math.floor(self.scroll)) - 1)
        hi = min(len(self.entries) - 1, int(math.ceil(self.scroll)) + self.cap)
        for i in range(lo, hi + 1):
            if i not in self.cache:
                _, name, path, isd = self.entries[i]
                el = Elt("item", path, name, self.dpr, isd, i)
                el.nav = bool(isd) and path != self.folder
                if self.is_open:                                    # scrolled in after the open animation
                    el.x = el.target = el.pending = 1.0
                self.cache[i] = el
        for i in [k for k in self.cache if k < lo - 2 or k > hi + 2]:
            del self.cache[i]

    # ---- open / close
    def _bars(self):
        """The pill-shaped elements at the top of the arc: 'Open in Explorer' and, inside a sub-folder, 'back'."""
        return [self.header] + ([self.back] if self.back is not None else [])

    def open_fan(self, folder, loc):
        if self.isVisible() and folder != self.root:                # switching stacks: hard swap
            self.hide_now()
        if not self.isVisible():
            self.root = self.folder = folder
            self.loc, self.stack, self.nav_to = loc, [], None
            self.is_open = False
            self.build(folder, loc)
            self.show()
            pin_topmost(self)
        self.unfold()

    def unfold(self):
        self.is_open = True
        self.t_open = now = time.perf_counter()
        spd = max(S["speed"], 0.1)
        for rank, i in enumerate(sorted(self.cache)):               # items unfold one after another...
            el = self.cache[i]
            el.pending, el.t_switch = 1.0, now + min(rank, self.cap) * STAG_OPEN / spd
        for k, el in enumerate(self._bars()):                       # ...but the pills don't wait for them
            el.pending, el.t_switch = 1.0, now + (2 + k) * STAG_OPEN / spd
        self.poll.start()
        self.start_timer()

    def close_fan(self, nav=False):
        if not nav:
            self.nav_to, self.stack = None, []                      # a real close forgets where we were
        if not self.isVisible() or self.header is None:
            return
        self.is_open = False
        self.poll.stop()
        now = time.perf_counter()
        spd = max(S["speed"], 0.1) * (2.0 if nav else 1.0)          # sub-folder swaps fold away quicker
        order = self._bars() + [self.cache[i] for i in sorted(self.cache, reverse=True)]   # pills first, nearest item last
        for rank, el in enumerate(order):
            el.pending, el.t_switch = 0.0, now + rank * STAG_CLOSE / spd
        self.start_timer()

    # ---- folders inside folders
    def navigate(self, path):
        """Open a sub-folder in place of this one: the fan folds away and unfolds the sub-folder."""
        if not self.is_open:
            return
        self.stack.append((self.folder, self.target))
        self.nav_to, self.restore = path, None
        self.close_fan(nav=True)

    def go_back(self):
        if not self.is_open or not self.stack:
            return
        self.nav_to, self.restore = self.stack.pop()
        self.close_fan(nav=True)

    def enter(self):
        path, self.nav_to = self.nav_to, None
        self.folder = path
        self.build(path, self.loc)
        if self.restore is not None:                                # coming back: land where you left off
            self.scroll = self.target = clamp(self.restore, 0.0, self.maxscroll)
            self.restore = None
            self.ensure_cache()
        self.unfold()

    def hide_now(self):
        self.stop_all()
        self.is_open = False
        self.hide()
        self.cache, self.header, self.back = {}, None, None
        self.stack, self.nav_to = [], None

    def check_dismiss(self):
        if time.perf_counter() - self.t_open < 0.3:
            return
        if key_down(0x1B):                                          # Esc
            return self.close_fan()
        bs = key_down(0x08)                                         # Backspace = back to the parent folder
        if bs and not self._bs and self.stack:
            self._bs = True
            return self.go_back()
        self._bs = bs
        if (key_down(0x01) or key_down(0x02)) and not self.region.contains(self.mapFromGlobal(QCursor.pos())):
            self.close_fan()                                        # click anywhere outside the fan

    def start_timer(self):
        if not self.timer.isActive():
            if not self.res_on:
                timer_resolution(True); self.res_on = True
            self.last = time.perf_counter()
            self.timer.start()

    def stop_all(self):
        self.timer.stop(); self.poll.stop()
        if self.res_on:
            timer_resolution(False); self.res_on = False

    # ---- layout: arc + push-apart magnification + edge fade
    def arc(self, s):
        th = s / self.R                                              # angle = arc length / radius
        return QPointF(self.origin.x() + self.bend * self.R * (1 - math.cos(th)),
                       self.origin.y() - self.start - self.R * math.sin(th))

    def fade(self, u):
        """Opacity from the item's rest position along the arc: fades past both ends, and hints at more content."""
        sp = self.sp
        ut = (self.cap - 1) * sp - u
        kb = clamp(self.scroll, 0.0, 1.0)                            # items exist below the viewport
        kt = clamp(self.maxscroll - self.scroll, 0.0, 1.0)           # items exist above the viewport
        ab = smooth(clamp((u + 0.6 * sp) / (0.6 * sp), 0, 1)) * (1 - kb * 0.55 * (1 - smooth(clamp(u / (1.4 * sp), 0, 1))))
        at = smooth(clamp((ut + 0.6 * sp) / (0.6 * sp), 0, 1)) * (1 - kt * 0.55 * (1 - smooth(clamp(ut / (1.4 * sp), 0, 1))))
        return ab * at

    def layout(self):
        """Magnified items take more room and push their neighbours outward along the arc (no overlap, ever).
        The item under the cursor stays put; the rest of the stack makes way."""
        sp, isz = self.sp, self.isz
        idxs = sorted(self.cache)
        if not idxs:
            return
        ex, extra, prev = {}, 0.0, None
        for i in idxs:
            el = self.cache[i]
            if prev is not None:
                extra += isz / 2 * ((self.cache[prev].hs - 1) + (el.hs - 1))
            ex[i] = extra
            prev = i
        head_extra = extra + isz / 2 * (self.cache[prev].hs - 1)
        delta = 0.0
        if self.is_open and self.mouse is not None:
            f = self.focus
            i0, t = math.floor(f), f - math.floor(f)
            lo_k, hi_k = idxs[0], idxs[-1]
            e0, e1 = ex[int(clamp(i0, lo_k, hi_k))], ex[int(clamp(i0 + 1, lo_k, hi_k))]
            delta = e0 * (1 - t) + e1 * t
        for i in idxs:
            el = self.cache[i]
            u = (i - self.scroll) * sp                               # rest position along the arc
            el.slot = self.arc(u + ex[i] - delta)
            el.edge = self.fade(u)
        count = min(len(self.entries), self.cap)
        self.header.slot = self.arc(count * sp + 10 + head_extra - delta)
        # keep every icon clear of the taskbar: magnification, push-apart, DPI scale or taskbar size can never overlap it
        limit, need = self.tb_y - 6, 0.0
        for i in idxs:
            el = self.cache[i]
            if el.edge > 0.25:
                need = max(need, el.slot.y() + self.isz * el.hs * (0.78 + 0.22 * el.edge) / 2 - limit)
        self.lift = max(need, self.lift + (need - self.lift) * 0.35)      # rises at once, settles smoothly
        if self.lift > 0.01:
            for el in list(self.cache.values()) + [self.header]:
                el.slot = QPointF(el.slot.x(), el.slot.y() - self.lift)
        if self.back is not None:
            h = self.header
            self.back.slot = QPointF(h.slot.x() - h.lw / 2 - self.back.lw / 2 - 12, h.slot.y())

    # ---- animation step (damped springs, dt-based so it stays smooth at any frame rate)
    def step(self):
        if self.header is None:
            return self.stop_all()
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        dts = dt * S["speed"]
        busy = False

        # scrolling: spring-chase with rubber-band at the ends, settles on a slot when you stop
        if self.maxscroll > 0 or self.scroll != 0.0:
            idle = now - self.t_wheel
            if idle > 0.35:
                self.target = float(round(clamp(self.target, 0.0, self.maxscroll)))
            elif idle > 0.12:
                self.target = clamp(self.target, 0.0, self.maxscroll)
            n = int(dt / 0.004) + 1
            h = dt / n
            for _ in range(n):
                self.sv += (SCROLL_K * (self.target - self.scroll) - SCROLL_C * self.sv) * h
                self.scroll += self.sv * h
            if abs(self.target - self.scroll) > 0.002 or abs(self.sv) > 0.01:
                busy = True
            else:
                self.scroll, self.sv = self.target, 0.0
            self.ensure_cache()

        # hover focus: where along the arc the cursor is -> gaussian magnification around it
        amp, f = 0.0, self.focus
        if self.is_open and self.mouse is not None:
            arg = clamp((self.origin.y() - self.start - self.mouse.y()) / self.R, -1.0, 1.0)
            sm = self.R * math.asin(arg)
            f = self.focus = self.scroll + sm / self.sp
            xm = self.origin.x() + self.bend * self.R * (1 - math.cos(sm / self.R))
            amp = S["magnify"] * math.exp(-((self.mouse.x() - xm) / 320.0) ** 2)

        for el in list(self.cache.values()) + self._bars():
            if el.t_switch is not None:
                if now >= el.t_switch:
                    el.target, el.t_switch = el.pending, None
                else:
                    busy = True
            c = C_OPEN if el.target > 0.5 else C_CLOSE
            n = int(dts / 0.004) + 1
            h = dts / n
            for _ in range(n):
                el.v += (K * (el.target - el.x) - c * el.v) * h
                el.x += el.v * h
            if abs(el.target - el.x) > 0.002 or abs(el.v) > 0.02:
                busy = True
            else:
                el.x, el.v = el.target, 0.0
            if el.kind in ("header", "back"):
                t = 1.06 if self.hover is el else 1.0
            else:
                d = (el.idx - f) * self.sp
                t = 1 + amp * math.exp(-(d / (1.5 * self.sp)) ** 2) * el.edge
                lt = 1.0 if (S["labels"] or self.hover is el) else 0.0
                el.lv += (lt - el.lv) * (1 - math.exp(-dt * 14))
                if abs(lt - el.lv) > 0.01:
                    busy = True
            el.hs += (t - el.hs) * (1 - math.exp(-dt * 16))
            if abs(t - el.hs) > 0.003:
                busy = True

        self.layout()
        if self.mouse is not None and self.is_open:
            self.hover = self.hit(self.mouse)
        self.update(self.bounds)
        if not busy:
            self.timer.stop()
            if self.res_on:
                timer_resolution(False); self.res_on = False
            if not self.is_open:
                if self.nav_to is not None:
                    self.enter()                                    # unfold the sub-folder in the same place
                else:
                    self.hide_now()

    # ---- geometry / hit testing
    def cur_pos(self, el):
        return QPointF(self.origin.x() + el.x * (el.slot.x() - self.origin.x()),
                       self.origin.y() + el.x * (el.slot.y() - self.origin.y()))

    def rects(self, el):
        pos = self.cur_pos(el)
        sc = (0.35 + 0.65 * clamp(el.x, 0.0, 1.1)) * el.hs * (0.78 + 0.22 * el.edge)
        if el.kind in ("header", "back"):
            w, h = el.lw * sc, el.lh * sc
            return None, QRectF(pos.x() - w / 2, pos.y() - h / 2, w, h)
        s = self.isz * sc
        icon = QRectF(pos.x() - s / 2, pos.y() - s / 2, s, s)
        lx = icon.left() - 8 - el.lw if self.label_side < 0 else icon.right() + 8
        return icon, QRectF(lx, pos.y() - el.lh / 2, el.lw, el.lh)

    def hit(self, pt):
        if self.header is None:
            return None
        cands = sorted(self.cache.values(), key=lambda q: q.hs) + self._bars()
        for el in reversed(cands):
            if el.x < 0.6 or el.edge < 0.35:
                continue
            icon, lab = self.rects(el)
            if icon is not None and icon.adjusted(-3, -3, 3, 3).contains(pt):
                return el
            if lab.contains(pt) and el.lv > 0.5:
                return el
        return None

    # ---- painting
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(e.rect(), QColor(0, 0, 0, 1))                    # alpha 1: invisible, but catches clicks
        if self.header is None:
            return
        for el in sorted(self.cache.values(), key=lambda q: q.hs) + self._bars():   # hovered item paints on top
            if el.x < 0.01 or el.edge < 0.01:
                continue
            icon, lab = self.rects(el)
            if icon is not None:
                p.setOpacity(clamp(el.x * 2.2, 0.0, 1.0) * el.edge)
                sh = QRectF(icon.center().x() - icon.width() * .46, icon.bottom() - icon.height() * .12,
                            icon.width() * .92, icon.height() * .22)
                g = QRadialGradient(sh.center(), sh.width() / 2)
                g.setColorAt(0, QColor(0, 0, 0, 120)); g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(g); p.drawEllipse(sh)
                p.drawPixmap(icon, el.icon, QRectF(el.icon.rect()))
            op = clamp((el.x - 0.05) * 1.6, 0.0, 1.0) * el.edge * el.lv
            if op > 0.01:
                p.setOpacity(op)
                m = el.lm * lab.width() / el.lw
                p.drawPixmap(lab.adjusted(-m, -m, m, m), el.label, QRectF(el.label.rect()))
        p.end()

    # ---- input
    def mouseMoveEvent(self, e):
        self.mouse = e.position()
        self.hover = self.hit(self.mouse) if self.is_open else None
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover else Qt.CursorShape.ArrowCursor)
        self.start_timer()

    def leaveEvent(self, e):
        self.mouse = self.hover = None
        self.start_timer()

    def wheelEvent(self, e):
        e.accept()
        if not self.is_open or self.maxscroll <= 0:
            return
        pd = e.pixelDelta().y()
        d = pd / self.sp if pd else e.angleDelta().y() / 120.0 * 1.6     # touchpads: pixels, wheels: ~1.6 items/notch
        if S["natural"]:
            d = -d
        if self.target < 0 or self.target > self.maxscroll:               # rubber-band resistance past the ends
            d *= 0.4
        self.target = clamp(self.target + d, -1.2, self.maxscroll + 1.2)
        self.t_wheel = time.perf_counter()
        self.start_timer()

    def mousePressEvent(self, e):
        if not self.is_open:
            return
        el = self.hit(e.position()) if e.button() == Qt.MouseButton.LeftButton else None
        if el is not None:
            if el.kind == "back":
                return self.go_back()
            if el.kind == "item" and el.nav and S["subfolders"]:
                return self.navigate(el.path)                       # dive into the folder, inside the fan
            open_path(el.path)                                      # a file, or "Open in Explorer"
        self.close_fan()
