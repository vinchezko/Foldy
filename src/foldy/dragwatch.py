"""Spring-loaded stacks: hold a dragged file over a pinned Foldy button and its fan opens, ready to take the drop.

Windows (11 especially) often refuses a drop straight onto a taskbar button, so the fan itself is the drop target:
drop on the fan to put the file in that folder, or on a folder inside the fan to put it in that sub-folder.

Only a plain poll of the left mouse button and the pointer position: no hooks, nothing is read from the drag itself.
It reacts only when the press began ABOVE the taskbar (so clicking, holding or re-ordering taskbar buttons never
triggers it) and the pointer then rests on a Foldy button for a moment.
"""
import os, re, time
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication
from .settings import RUNTIME, log
from .winutil import _BTN_CACHE, enum_taskbar_buttons, key_down, pick_button, taskbar_rect, uia_button_at

DWELL = 0.1                                       # seconds the pointer rests on the button before the fan opens
_ID = re.compile(r"foldy\.([0-9a-f]{10})")


def cursor_px():
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return None


def primary_vk():
    try:
        import ctypes
        return 0x02 if ctypes.windll.user32.GetSystemMetrics(23) else 0x01      # honour swapped mouse buttons
    except Exception:
        return 0x01


def inside(rect, pt, slack=3):
    l, t, r, b = rect
    return l - slack <= pt[0] <= r + slack and t - slack <= pt[1] <= b + slack


def base_of(folder):
    return os.path.basename(folder.rstrip("\\/")).lower()


def locate(buttons, pt, ids):
    """(folder, rect) of the Foldy button under pt, using the same evidence the click path trusts: the button's
    AppUserModelID, then its name (the shortcut's name is the folder's name); names are matched leniently so Windows
    builds that decorate them ('Downloads pinned', 'Downloads - 1 window') still work."""
    under = [b for b in buttons if inside(b["rect"], pt, 2)]
    for b in under:                                                 # 1) identity
        m = _ID.search(b["aid"])
        if m and m.group(1) in ids:
            return ids[m.group(1)], b["rect"]
    for fid, f in ids.items():                                      # 2) the proven selection used when a stack is opened
        r = pick_button(buttons, "Foldy." + fid, base_of(f))
        if r and inside(r, pt, 4):
            return f, r
    for b in under:                                                 # 3) lenient name match, only if it is unambiguous
        hits = [f for f in ids.values() if base_of(f) and base_of(f) in b["name"]]
        if len(set(hits)) == 1:
            return hits[0], b["rect"]
    return None, None


class DragWatch(QObject):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.origin = self.t_on = None
        self.fired, self.t_fire, self.t_try, self.logs = False, 0.0, 0.0, 0
        self.rects, self.t_rects, self.learned = [], 0.0, False      # [(folder, rect)] of our buttons, learned when a drag starts
        self.nlog, self.said, self.on_bar = 0, False, False
        self.timer = QTimer(self, interval=30)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def say(self, text):
        if self.nlog < 60:
            self.nlog += 1
            log("dragwatch: " + text)

    def learn(self, tb, ids):
        """Read every Foldy button's position once, as soon as a drag starts, so that reaching a button needs no lookups."""
        self.t_rects, self.learned = time.monotonic(), True
        buttons = enum_taskbar_buttons(tb) or []
        found = []
        for fid, f in ids.items():
            r = pick_button(buttons, "Foldy." + fid, base_of(f))
            if r:
                found.append((f, r))
                _BTN_CACHE["foldy." + fid] = r
        if found:
            self.rects = found
        self.say(f"learned {len(found)} of {len(ids)} Foldy buttons ({len(buttons)} taskbar buttons seen)")

    def tick(self):
        h = self.hub
        if RUNTIME["uninstalling"]:
            return
        if not key_down(primary_vk()):                              # nothing held: reset
            self.origin = self.t_on = None
            self.fired = self.learned = self.said = self.on_bar = self._same_said = False
            return
        if not h._stacks:
            if not getattr(self, "_idle_said", False):
                self._idle_said = True
                self.say("idle: no pinned Foldy stacks are known yet")
            return
        pt = cursor_px()
        if pt is None:
            return
        if self.origin is None:
            self.origin = pt
        now = time.monotonic()
        ov = h.drop_fan
        if self.fired:
            if ov.is_open or now - self.t_fire < 0.6:
                return
            self.fired = False                                      # the fan folded away (drag left it): allow it to open again
            self.t_on = None
        tb = taskbar_rect()
        if not tb or tb[1] < 100 or self.origin[1] >= tb[1] - 4:    # no bottom taskbar, or the press began on the bar
            self.t_on = None
            if not self.said and abs(pt[0] - self.origin[0]) + abs(pt[1] - self.origin[1]) > 14:
                self.said = True
                self.say(f"ignored: press began at {self.origin}, taskbar={tb[:4] if tb else None}")
            return
        own = h.overlay.dragging                                    # a drag out of a fan: its modal loop is ours, so no UI Automation now
        ids = h.stack_ids()
        if (not self.learned and not own and abs(pt[0] - self.origin[0]) + abs(pt[1] - self.origin[1]) > 14
                and now - self.t_rects > 3.0):
            self.learn(tb, ids)                                     # (a few ms, once per drag)
        if not self.said and abs(pt[0] - self.origin[0]) + abs(pt[1] - self.origin[1]) > 14:
            self.said = True
            self.say(f"drag started at {self.origin}; stacks={len(ids)}; own={own}; taskbar={tb[:4]}")
        if pt[1] < tb[1]:
            self.t_on = None
            return
        if not self.on_bar:
            self.on_bar = True
            self.say(f"pointer reached the taskbar at {pt}; learned={[(base_of(f), r) for f, r in self.rects]}; cached={len(_BTN_CACHE)}")
        if self.t_on is None:
            self.t_on = now
            return
        folder = rect = None
        for f, r in self.rects:                                     # 1) positions learned at the start of this drag: instant
            if inside(r, pt, 2):
                folder, rect = f, r
                break
        if not folder:                                              # 2) where we last saw a Foldy button
            for key, r in _BTN_CACHE.items():
                m = _ID.search(key)
                if m and m.group(1) in ids and inside(r, pt, 14):
                    folder, rect = ids[m.group(1)], r
                    break
        if not folder and not own and now - self.t_try >= 0.2 and now - self.t_on >= DWELL:   # 3) ask Windows right now
            self.t_try = now
            one = uia_button_at(pt[0], pt[1], tb)
            allb = enum_taskbar_buttons(tb) or []
            folder, rect = locate(([one] if one else []) + allb, pt, ids)
            if self.logs < 8:
                self.logs += 1
                under = [(b["aid"][:34], b["name"][:26]) for b in allb if inside(b["rect"], pt, 2)]
                log(f"dragwatch: pointer {pt}; stacks={[base_of(f) for f in ids.values()]}; under pointer={under}; matched={folder}")
        if not folder or now - self.t_on < 0.04:
            return
        src = h.overlay.drag_el                                     # the item being carried out of a fan
        if src is not None and h.overlay.dragging and not h.overlay.is_open and h.overlay.root == folder:
            self.fired, self.t_fire = True, now                     # it folded away while carried: bring that same fan back
            l, t, r, b = rect
            dpr = QApplication.primaryScreen().devicePixelRatio()
            self.say(f"carried file is back on {base_of(folder)}: reopening its fan")
            h.overlay.reopen_drag(folder, {"cx": (l + r) / 2 / dpr, "cy": (t + b) / 2 / dpr, "tb_top": tb[1] / dpr, "exact": True})
            return
        if src is not None and os.path.normcase(os.path.dirname(os.path.abspath(src.path))) == os.path.normcase(os.path.abspath(folder)):
            if self.nlog < 60 and not getattr(self, "_same_said", False):
                self._same_said = True
                self.say(f"ignored: {base_of(folder)} is where the carried item already is")
            return
        self.fired, self.t_fire = True, now
        self.say(f"on the button of {base_of(folder)}: opening its fan")
        if not (ov.is_open and ov.root == folder):
            l, t, r, b = rect
            dpr = QApplication.primaryScreen().devicePixelRatio()
            ov.open_fan(folder, {"cx": (l + r) / 2 / dpr, "cy": (t + b) / 2 / dpr, "tb_top": tb[1] / dpr, "exact": True})
