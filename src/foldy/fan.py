"""The fan overlay: arc layout, spring animation, push-apart magnification and kinetic scrolling."""
import math, os, time, traceback
from PyQt6.QtCore import QFileInfo, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, QTimer, QUrl, Qt
from PyQt6.QtGui import (QColor, QCursor, QDrag, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient, QRegion)
from PyQt6.QtWidgets import QApplication, QWidget
from .constants import (BASE_ICON, BASE_SP, C_CLOSE, C_OPEN, K, SCROLL_C, SCROLL_K, STAG_CLOSE, STAG_OPEN,
                        WIN_W)
from . import dropzone
from . import render
from .cancel_corner import corner
from .render import Elt, entries_for, glass_label
from .settings import S, log
from .util import clamp, smooth
from .winutil import key_down, open_path, pin_topmost, set_click_through, timer_resolution, window_at_cursor


SPRING_T = {"in": 0.75, "back": 0.55}                         # seconds a carried file must rest on a folder / the back pill


class FanOverlay(QWidget):
    """Small fixed-size window just big enough for the fan. Never takes focus; clicks pass through everywhere
    except the fan itself and the clicked button (window mask). Items are laid out along a circular arc."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)                                   # files dragged over the open fan can be dropped on it
        self.on_drop = None                                         # hub callback: (folder, paths, mods)
        self.drop_mode = False                                      # this overlay only exists to take drops (see dragwatch)
        self.entries, self.cache, self.header = [], {}, None
        self.folder, self.is_open = None, False
        self.root, self.loc, self.back = None, {}, None              # pinned folder, where it opened, the 'back' pill
        self.stack, self.nav_to, self.restore = [], None, None       # folders-in-folders: ancestors, target, scroll to restore
        self._bs = False
        self.press, self.dragging, self.drag_el = None, False, None   # click-or-drag: pressed item, drag-out state
        self.drag_over, self.dropbar, self.ct = False, None, False  # a file is being dragged over the fan; its 'drop here' pill
        self.spring_key, self.spring_t = None, 0.0                  # dwell on a folder / the back pill while dragging
        self.away_native = 0.0                                      # time a carried file has spent away from the fan
        self.cancelled, self.idrag_up = False, 0                    # Esc / right-click during a shell drag; polls that saw the button up
        self.t_top, self.on_note = 0.0, None                        # last time we re-asserted 'topmost'; hub callback for messages
        self.idrag, self.idrag_pos, self.away_t = None, QPointF(), 0.0   # in-fan drag (no OS drag yet), its pointer, time spent away from the fan
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
        self.drag_timer = QTimer(self, interval=30)                 # drives hover + spring-loaded folders during a drag
        self.drag_timer.timeout.connect(self.drag_tick)
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
        self.dropbar = None
        if self.drop_mode or self.dragging or self.drag_over or self.idrag is not None:   # the 'drop here' placeholder
            self.dropbar = Elt("drop", folder, self.drop_text(folder), self.dpr)
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
        """The pill-shaped elements at the top of the arc: 'Open in Explorer', 'back' (inside a sub-folder) and, while a
        file is being dragged, the 'drop here' placeholder."""
        return [self.header] + ([self.back] if self.back is not None else []) + ([self.dropbar] if self.dropbar is not None else [])

    def drop_text(self, folder):
        return "↓  Drop in  " + (os.path.basename(folder.rstrip("\\/")) or folder)

    def show_dropbar(self, on):
        if self.header is None:
            return
        if on and self.dropbar is None:
            self.dropbar = Elt("drop", self.folder, self.drop_text(self.folder), self.dpr)
        if self.dropbar is not None:
            self.dropbar.pending, self.dropbar.t_switch = (1.0 if on else 0.0), time.perf_counter()
        self.start_timer()

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
        spd = max(S["speed"], 0.1) * ((3.0 if self.carrying() else 2.0) if nav else 1.0)   # sub-folder swaps fold away quicker
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
        self.cache, self.header, self.back, self.dropbar = {}, None, None, None
        self.stack, self.nav_to = [], None
        if self.idrag is not None:
            log("idrag: ended because the fan was hidden")
        self.press = None
        self.drag_over, self.spring_key, self.idrag, self.away_t = False, None, None, 0.0
        if not self.dragging:
            self.drag_el = None                                     # (a running shell drag keeps remembering what it carries)
        self.away_native = 0.0
        if self.dragging:
            log("fan hidden while a shell drag is still running (the cancel corner stays until it ends)")
        else:
            corner().activate(False)                                # (a running drag still needs its ✕)
        self.drag_timer.stop()

    def check_dismiss(self):
        if self.idrag is not None:
            self.idrag_up = 0 if key_down(0x01) else self.idrag_up + 1
            if self.idrag_up >= 3:                                  # released somewhere we never heard about (3 polls: never beat the real release event)
                log("idrag: button was released outside the window; cancelled")
                self.idrag_cancel()
        if self.dragging or self.idrag is not None or time.perf_counter() - self.t_open < 0.3:   # never close under a drag in progress
            return
        if key_down(0x1B):                                          # Esc
            return self.close_fan()
        bs = key_down(0x08)                                         # Backspace = back to the parent folder
        if bs and not self._bs and self.stack:
            self._bs = True
            return self.go_back()
        self._bs = bs
        pt = QPointF(self.mapFromGlobal(QCursor.pos()))
        inside = self.region.contains(pt.toPoint())
        if (self.drop_mode or self.drag_over) and time.perf_counter() - self.t_top > 0.3:
            self.t_top = time.perf_counter()
            pin_topmost(self)                                       # the taskbar re-raises itself during drags: stay above it
        if self.drop_mode or self.drag_over:                        # a file is being dragged over the fan: close when it moves away from it
            if self.is_open and self.nav_to is None:
                now = time.perf_counter()
                if self.near(pt, 70):
                    self.away_t = 0.0
                elif not self.away_t:
                    self.away_t = now
                elif now - self.away_t > 0.18:
                    self.away_t = 0.0
                    self.close_fan()
            return
        if (key_down(0x01) or key_down(0x02)) and not inside:
            self.close_fan()                                        # click anywhere outside the fan

    def start_timer(self):
        if not self.timer.isActive():
            if not self.res_on:
                timer_resolution(True); self.res_on = True
            self.last = time.perf_counter()
            self.timer.start()

    def stop_all(self):
        self.timer.stop(); self.poll.stop(); self.drag_timer.stop()
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
        if self.carrying():                                         # carrying: scale in place, never push neighbours (targets hold still)
            ex, head_extra = {i: 0.0 for i in ex}, 0.0
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
        if self.dropbar is not None:                                # stacked above the header, spaced by the pills' real heights
            gap = (self.header.lh + self.dropbar.lh) * 1.06 / 2 + 18
            self.dropbar.slot = QPointF(self.header.slot.x(), self.header.slot.y() - gap)
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
        carry = self.carrying()
        if self.is_open and self.mouse is not None:                 # (while carrying: a gentler magnify, and nothing is pushed aside)
            arg = clamp((self.origin.y() - self.start - self.mouse.y()) / self.R, -1.0, 1.0)
            sm = self.R * math.asin(arg)
            f = self.focus = self.scroll + sm / self.sp
            xm = self.origin.x() + self.bend * self.R * (1 - math.cos(sm / self.R))
            amp = S["magnify"] * math.exp(-((self.mouse.x() - xm) / 320.0) ** 2) * (0.55 if carry else 1.0)

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
            fill = 0.0                                              # how much of the blue border is drawn: the dwell timer itself
            if carry and self.hover is el and self.is_open and self.nav_to is None:
                sk = self.spring_key_of(el)
                if sk is not None and sk == self.spring_key:
                    fill = clamp((now - self.spring_t) / SPRING_T[sk[0]], 0.0, 1.0)
            if fill >= el.fillk:
                el.fillk = fill
            else:
                el.fillk += (fill - el.fillk) * (1 - math.exp(-dt * 16))    # leaving: the border runs back
                if el.fillk < 0.01:
                    el.fillk = 0.0
            if fill > 0 or el.fillk > 0:
                busy = True
            if el.kind in ("header", "back", "drop"):
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

        db = self.dropbar
        if db is not None and not (self.drop_mode or self.dragging or self.drag_over or self.idrag is not None) and db.target == 0 and db.t_switch is None and db.x <= 0.01:
            self.dropbar = None                                     # the placeholder has folded away
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
        if el.kind in ("header", "back", "drop"):
            w, h = el.lw * sc, el.lh * sc
            return None, QRectF(pos.x() - w / 2, pos.y() - h / 2, w, h)
        s = self.isz * sc
        icon = QRectF(pos.x() - s / 2, pos.y() - s / 2, s, s)
        lx = icon.left() - 8 - el.lw if self.label_side < 0 else icon.right() + 8
        return icon, QRectF(lx, pos.y() - el.lh / 2, el.lw, el.lh)

    def carrying(self):
        """Something is being dragged to / from this fan: freeze the layout so targets hold still under the pointer."""
        return self.dragging or self.idrag is not None or self.drag_over or self.drop_mode

    def footprint(self):
        """Bounding box of what the fan really shows (icons, labels, pills), or None."""
        bb = None
        for el in list(self.cache.values()) + self._bars():
            if el.x < 0.3 or el.edge < 0.2:
                continue
            for r in self.rects(el):
                if r is not None:
                    bb = r if bb is None else bb.united(r)
        return bb

    def near(self, pt, slack=60.0):
        """Is the pointer within `slack` px of what the fan really shows (its icons, pills and the pinned button)?
        The window itself is a big invisible box; this is the real footprint."""
        if self.header is None:
            return False
        bb = QRectF(self.origin.x() - 44, self.tb_y - 10, 88, self.height() - self.tb_y + 10)     # the pinned button
        fp = self.footprint()
        if fp is not None:
            bb = bb.united(fp)
        return bb.adjusted(-slack, -slack, slack, slack).contains(pt)

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
    @staticmethod
    def progress_border(p, r, rad, k):
        """A blue border that draws itself around `r`, from the top middle clockwise, one direction only, until it closes at k = 1."""
        r = QRectF(r).adjusted(.9, .9, -.9, -.9)
        rad = min(rad, r.height() / 2, r.width() / 2)
        x, y, w, h, d, cx = r.left(), r.top(), r.width(), r.height(), rad * 2, r.center().x()
        path = QPainterPath()
        path.moveTo(cx, y); path.lineTo(x + w - rad, y); path.arcTo(x + w - d, y, d, d, 90, -90)
        path.lineTo(x + w, y + h - rad); path.arcTo(x + w - d, y + h - d, d, d, 0, -90)
        path.lineTo(x + rad, y + h); path.arcTo(x, y + h - d, d, d, 270, -90)
        path.lineTo(x, y + rad); path.arcTo(x, y, d, d, 180, -90); path.lineTo(cx, y)
        pen = QPen(QColor(120, 185, 255, 245), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if k < 0.999:
            pen.setDashPattern([max(path.length() * k, 0.01) / pen.widthF(), 100000.0])
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.drawPath(path)
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
            ghost = 0.3 if self.is_dragged(el) else 1.0                  # the item you are carrying away stays as a faint ghost
            if icon is not None:
                p.setOpacity(clamp(el.x * 2.2, 0.0, 1.0) * el.edge * ghost)
                sh = QRectF(icon.center().x() - icon.width() * .46, icon.bottom() - icon.height() * .12,
                            icon.width() * .92, icon.height() * .22)
                g = QRadialGradient(sh.center(), sh.width() / 2)
                g.setColorAt(0, QColor(0, 0, 0, 120)); g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(g); p.drawEllipse(sh)
                p.drawPixmap(icon, el.icon, QRectF(el.icon.rect()))
            op = clamp((el.x - 0.05) * 1.6, 0.0, 1.0) * el.edge * el.lv * ghost
            if op > 0.01:
                p.setOpacity(op)
                m = el.lm * lab.width() / el.lw
                p.drawPixmap(lab.adjusted(-m, -m, m, m), el.label, QRectF(el.label.rect()))
                rad = 8.0 * lab.width() / el.lw
                if el.kind == "drop":                                # the drop pill: static; a plain blue border only while hovered
                    if self.hover is el and self.carrying():
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.setPen(QPen(QColor(120, 185, 255, 235), 1.8))
                        p.drawRoundedRect(lab.adjusted(.9, .9, -.9, -.9), rad, rad)
                elif el.fillk > 0.01 and el.kind in ("back", "item"):   # resting on a folder / the back pill: the border draws itself
                    self.progress_border(p, lab, rad, el.fillk)
        if self.idrag is not None:                                  # the item you are carrying, under the pointer
            s = self.isz * 1.35
            c = self.idrag_pos
            r = QRectF(c.x() - s / 2, c.y() - s / 2, s, s)
            p.setOpacity(0.35)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0))
            p.drawEllipse(QRectF(r.left() + s * .1, r.bottom() - s * .1, s * .8, s * .16))
            p.setOpacity(0.96)
            p.drawPixmap(r, self.idrag.icon, QRectF(self.idrag.icon.rect()))
        p.end()

    # ---- input
    def can_drag(self, el):
        """Files and folders can be dragged out; the pills and the 'Folder is empty' placeholder cannot."""
        return el.kind == "item" and el.path != self.folder and os.path.exists(el.path)

    def drag_image(self, el):
        """The picture that follows the pointer while a file is carried: a big icon with its name under it.
        -> QImage (premultiplied ARGB, device pixels) and the hot spot (the middle of the icon)."""
        ISZ = 112
        icon = QPixmap()
        try:
            icon = render.ICONS.icon(QFileInfo(el.path)).pixmap(QSize(128, 128))       # the largest shell icon available
        except Exception:
            pass
        if icon.isNull():
            icon = el.icon
        lab, lw, lh, lm = glass_label(os.path.basename(el.path.rstrip("\\/")) or el.path, 1.0)
        W, H = max(ISZ + 16, lab.width() + 4), ISZ + 8 + lab.height()
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        ix = (W - ISZ) // 2
        sh = QRectF(ix + ISZ * .1, ISZ * .86, ISZ * .8, ISZ * .16)                       # soft contact shadow
        g = QRadialGradient(sh.center(), sh.width() / 2)
        g.setColorAt(0, QColor(0, 0, 0, 110)); g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(g); p.drawEllipse(sh)
        p.drawPixmap(QRect(ix, 0, ISZ, ISZ), icon)
        p.drawPixmap((W - lab.width()) // 2, ISZ + 8 - lm, lab)
        p.end()
        return img, QPoint(W // 2, ISZ // 2)

    def start_drag(self, el):
        """Carry a real file/folder out of the fan: into a browser upload, a chat, an editor, an Explorer window, or onto a
        folder / the back pill of this very fan. Uses the shell's own data object (what Explorer uses)."""
        self.press, self.dragging, self.drag_el, self.idrag = None, True, el, None
        self.cancelled, self.ntog = False, 0
        self.hover, self.mouse = None, None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.ct = True
        corner().activate(True)
        set_click_through(self, True)                              # the fan must never sit between the file and its target...
        self.show_dropbar(True)                                    # ...except over its own folders, back pill and drop pill
        self.spring_key = None
        self.drag_timer.start()
        self.start_timer()
        name = os.path.basename(el.path)
        try:
            image = None
            try:
                img, hot = self.drag_image(el)
                ptr = img.constBits()
                image = (img.width(), img.height(), bytes(ptr.asstring(img.sizeInBytes())), hot.x(), hot.y())
            except Exception:
                log("drag image failed:\n" + traceback.format_exc())
            try:
                effect = dropzone.native_drag(el.path, image)
                log(f"drag-out (native): {name} -> effect {effect}; cancelled={self.cancelled}; released over {window_at_cursor()}")
                if effect == 0 and not self.cancelled and self.is_open:
                    pt = QPointF(self.mapFromGlobal(QCursor.pos()))  # nobody took it: was it let go on one of our own targets?
                    tgt = self.hit(pt) if self.region.contains(pt.toPoint()) else None
                    if not self.is_drop_el(tgt):
                        log(f"drag-out: nothing took it; pointer on {getattr(tgt, 'kind', None)} {getattr(tgt, 'name', '')!r}")
                    if self.is_drop_el(tgt):
                        log(f"drag-out: the shell found no taker but it was let go on {tgt.kind} {tgt.name!r}; dropping it ourselves")
                        self.finish_drop(self.drop_target(tgt), el.path)
            except Exception as ex:
                log(f"drag-out: native route failed ({ex!r}); trying pywin32")
                ok, res = dropzone.shell_drag(el.path)
                log(f"drag-out (pywin32): {name} -> {res}" if ok else f"drag-out: pywin32 route failed ({res})")
        except Exception:
            log("drag-out failed:\n" + traceback.format_exc())
        finally:
            self.drag_timer.stop()
            corner().activate(False)
            set_click_through(self, False)
            self.ct = False
            self.dragging, self.drag_el, self.press, self.spring_key = False, None, None, None
            if self.is_open:
                self.close_fan()                                       # the job is done: fold the fan away

    def is_dragged(self, el):
        """Is this element the item being carried? By path, because the elements are rebuilt whenever the fan goes into a
        sub-folder or back, and the carried item must stay grey (and never be a target for itself) all that time."""
        d = self.drag_el
        return d is not None and el is not None and el.kind == "item" and os.path.normcase(el.path) == os.path.normcase(d.path)

    def is_drop_el(self, el):
        """Elements a dragged file can be dropped on: a folder (goes inside it), the back pill (goes up one level), the
        drop pill (goes into the folder being shown)."""
        return el is not None and (el.kind in ("drop", "back") or (el.kind == "item" and el.nav and not self.is_dragged(el)))

    def spring_key_of(self, el):
        if el is not None and el.kind == "item" and el.nav and not self.is_dragged(el):
            return ("in", el.path)
        if el is not None and el.kind == "back":
            return ("back", None)
        return None

    def spring(self, el):
        """Spring-loaded folders: rest a dragged file on a folder and the fan opens it; rest it on the back pill and the
        fan goes back up. The placeholder follows, so a drop always goes where the pill says."""
        key = self.spring_key_of(el)
        now = time.perf_counter()
        if key != self.spring_key:
            self.spring_key, self.spring_t = key, now
            return
        if key is None or not self.is_open or self.nav_to is not None:
            return
        if now - self.spring_t >= SPRING_T[key[0]]:
            log(f"spring: {'into ' + os.path.basename(key[1].rstrip(chr(92) + '/')) if key[0] == 'in' else 'back up one level'}")
            self.spring_key = None
            self.hover = None
            self.navigate(key[1]) if key[0] == "in" else self.go_back()

    def drag_tick(self):
        if not (self.dragging or self.drag_over or self.idrag is not None) or self.header is None:
            return self.drag_timer.stop()
        if self.dragging:                                           # our own drag: the shell owns the mouse, so poll it
            if key_down(0x1B) or key_down(0x02):
                self.cancelled = True                               # Esc / right-click cancel a shell drag: never "finish" those ourselves
            pt = QPointF(self.mapFromGlobal(QCursor.pos()))
            inside = self.is_open and self.region.contains(pt.toPoint())
            self.mouse = pt if inside else None
            self.hover = self.hit(pt) if inside else None
            if self.is_open and self.near(pt, 60):
                self.away_native = 0.0
            elif self.is_open:
                self.away_native = self.away_native or time.perf_counter()
                if time.perf_counter() - self.away_native > 0.8:    # carried away and left alone: fold the fan back
                    self.away_native = 0.0
                    self.close_fan()
            want = self.is_drop_el(self.hover)                      # solid only over things that can take the file
            if want == self.ct:
                self.ct = not want
                set_click_through(self, self.ct)
                self.ntog = getattr(self, "ntog", 0) + 1
                if self.ntog <= 12:                                 # (the log must not fill up with every flip)
                    log(f"drag: fan is now {'click-through' if self.ct else 'solid'} (pointer on {getattr(self.hover, 'kind', None)})")
        self.spring(self.hover if self.is_open else None)
        self.start_timer()

    def reopen_drag(self, folder, loc):
        """The fan folded away while its file is still on the cursor, and the file came back to the taskbar button:
        unfold the very same fan again, ready to take the file."""
        if not self.dragging or self.is_open:
            return
        self.away_native = 0.0
        self.open_fan(folder, loc)
        self.ct = True
        set_click_through(self, True)
        self.drag_timer.start()
        log(f"drag: fan reopened for the carried file ({os.path.basename(folder.rstrip(chr(92) + '/')) or folder})")

    def begin_idrag(self, el, pos):
        """Pick an item up INSIDE the fan. No operating-system drag yet: the icon simply follows the pointer, so dropping
        on a folder / the back pill / the drop pill is fully ours. Pulling away from the fan hands over to a real drag."""
        self.press, self.idrag, self.drag_el, self.idrag_pos = None, el, el, pos
        self.spring_key, self.idrag_up = None, 0
        log(f"idrag: picked up {os.path.basename(el.path)}")
        corner().activate(True)                                     # the ✕ appears in the screen corner
        self.show_dropbar(True)
        self.drag_timer.start()
        self.start_timer()

    def idrag_cancel(self):
        self.idrag = None
        if not self.dragging:
            self.drag_el = None
        self.spring_key = None
        self.drag_timer.stop()
        if not self.dragging:
            corner().activate(False)
        if self.is_open and not self.drop_mode:
            self.show_dropbar(False)
        self.update()

    def finish_drop(self, dest, path):
        """Our own drop of one carried item onto `dest` (no operating-system drop involved)."""
        if not dest or not self.on_drop:
            return False
        mods = dropzone.current_mods()
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(dest) and not (mods & 1):
            log(f"drop: {os.path.basename(path)} is already in {os.path.basename(dest.rstrip(chr(92) + '/')) or dest}; nothing to do")
            return False                                            # dropped back where it already is
        log(f"drop: {os.path.basename(path)} -> {dest} (mods={mods})")
        self.on_drop(dest, [path], mods)
        return True

    def idrag_end(self, pos):
        el = self.idrag
        if self.is_open:
            tgt = self.hit(pos)
            dest = self.drop_target(tgt) if self.is_drop_el(tgt) else None
            log(f"idrag: released on {getattr(tgt, 'kind', None)} ({getattr(tgt, 'name', '')!r}) -> {dest}")
        else:
            dest = self.nav_to                                      # let go while the fan was sliding into a folder: it goes in there
            log(f"idrag: released while the fan was moving -> {dest}")
        self.idrag_cancel()
        if self.finish_drop(dest, el.path):
            self.close_fan()

    def mouseMoveEvent(self, e):
        self.mouse = e.position()
        if self.idrag is not None:
            if not (e.buttons() & Qt.MouseButton.LeftButton):
                log("idrag: mouse move without the left button; cancelled")
                return self.idrag_cancel()
            self.idrag_pos = e.position()
            if self.is_open and not self.near(self.idrag_pos, 110) and not self.region.contains(self.idrag_pos.toPoint()):
                el = self.idrag                                     # pulled well away from the fan: hand over to a real file drag
                log(f"idrag: handed to the shell at {self.idrag_pos.x():.0f},{self.idrag_pos.y():.0f} (outside the fan)")
                self.idrag = None
                return self.start_drag(el)
            self.hover = self.hit(self.mouse) if self.is_open else None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.spring(self.hover)
            self.start_timer()
            self.update()
            return
        if self.press is not None and self.is_open and (e.buttons() & Qt.MouseButton.LeftButton):
            el, p0 = self.press
            if (e.position() - p0).manhattanLength() >= QApplication.startDragDistance() and self.can_drag(el):
                return self.begin_idrag(el, e.position())
        self.hover = self.hit(self.mouse) if self.is_open else None
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover else Qt.CursorShape.ArrowCursor)
        self.start_timer()

    # ---- files dropped ON the fan (held over a pinned button, dragged from another app, or from this very fan)
    def drop_target(self, el):
        """Folder a drop lands in: the folder under the pointer, the parent for the back pill, else the folder shown."""
        if el is not None and el.kind == "back" and self.stack:
            return self.stack[-1][0]
        if el is not None and el.kind == "item" and el.nav and not self.is_dragged(el):
            return el.path
        return self.folder

    def dlog(self, what):
        log(f"fan-drop {what}: root={os.path.basename(self.root or '')} open={self.is_open} drop_mode={self.drop_mode} "
            f"own={self.dragging} hover={getattr(self.hover, 'kind', None)}")

    def dragEnterEvent(self, e):
        if not self.isVisible():
            return e.ignore()
        if not self.dragging:
            self.drag_over = True
            self.show_dropbar(True)
            self.drag_timer.start()
        self.mouse = e.position()
        e.setDropAction(Qt.DropAction.CopyAction)                   # we do the move/copy ourselves: the source must not delete anything
        e.accept()                                                  # always: a cross over the fan is never right
        self.dlog("enter" + ("" if e.mimeData().hasUrls() else " (no file urls!)"))
        self.start_timer()

    def dragMoveEvent(self, e):
        self.mouse = e.position()
        self.hover = self.hit(self.mouse) if self.is_open else None
        ok = self.isVisible() and (not self.dragging or self.is_drop_el(self.hover))
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept() if ok else e.ignore()
        self.start_timer()

    def dragLeaveEvent(self, e):
        self.mouse = self.hover = None
        self.spring_key = None
        self.dlog("leave")
        if not self.dragging:                                       # a file was carried away from the fan: fold it back
            self.drag_over = False
            if self.is_open:
                self.close_fan()
        self.start_timer()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        dest = self.drop_target(self.hit(e.position())) if self.is_open else (self.nav_to or self.folder)
        km = QApplication.keyboardModifiers()
        mods = (1 if km & Qt.KeyboardModifier.ControlModifier else 0) | (2 if km & Qt.KeyboardModifier.ShiftModifier else 0)
        self.dlog(f"drop paths={len(paths)} dest={os.path.basename(dest or '')}")
        own_noop = self.dragging and not (mods & 1) and all(os.path.dirname(os.path.abspath(p)) == os.path.abspath(dest or "") for p in paths)
        if not paths and self.on_note:
            self.on_note("Couldn't read what was dropped (it isn't a normal file or folder).")
        elif paths and dest and self.on_drop and not own_noop:
            self.on_drop(dest, paths, mods)
        self.drag_over = False
        self.close_fan()

    def leaveEvent(self, e):
        if self.idrag is not None:                                  # (the mouse is captured while carrying an item)
            return
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
        self.press = None
        el = self.hit(e.position()) if e.button() == Qt.MouseButton.LeftButton else None
        if el is None:
            return self.close_fan()
        self.press = (el, e.position())                             # decided on release (click) or on move (drag out)

    def mouseReleaseEvent(self, e):
        if self.idrag is not None:
            return self.idrag_end(e.position())
        pr, self.press = self.press, None
        if pr is None or not self.is_open or e.button() != Qt.MouseButton.LeftButton:
            return
        el, p0 = pr
        if (e.position() - p0).manhattanLength() >= QApplication.startDragDistance():
            return                                                  # it was a drag that didn't leave: not a click
        if el.kind == "back":
            return self.go_back()
        if el.kind == "item" and el.nav and S["subfolders"]:
            return self.navigate(el.path)                           # dive into the folder, inside the fan
        open_path(el.path)                                          # a file, or "Open in Explorer"
        self.close_fan()
