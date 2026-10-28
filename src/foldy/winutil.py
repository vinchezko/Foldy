"""Windows helpers: paths, autostart, taskbar geometry, UI Automation lookup and the click tracker."""
import os, re, subprocess, sys, threading, time, traceback
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication
from .constants import APP, INSTALL_DIR, RUN_KEY
from .settings import log


SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))        # .../src
REPO = os.path.dirname(SRC)
_data_dir = None


def asset(name):
    """A bundled file: next to the exe when frozen, in the repo's assets/ folder during development."""
    base = getattr(sys, "_MEIPASS", None)
    return os.path.join(base, name) if base else os.path.join(REPO, "assets", name)


def docs_path():
    """Documents\\Foldy (path only - does not create anything)."""
    try:
        from win32com.shell import shell, shellcon
        docs = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, 0, 0)
    except Exception:
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs, "Foldy")


def data_dir():
    """Documents\\Foldy - holds every pinned shortcut and its icon."""
    global _data_dir
    if _data_dir is None:
        _data_dir = docs_path()
        os.makedirs(os.path.join(_data_dir, "Icons"), exist_ok=True)
    return _data_dir


def start_menu_lnk():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs", "Foldy.lnk")


def shortcut_cmd(extra):
    """What a pinned button runs: the tiny pre-installed launcher (starts in ~100 ms), never the big one-file exe."""
    if getattr(sys, "frozen", False):
        fast = os.path.join(INSTALL_DIR, "launcher", "fsl.exe")
        return (fast, extra) if os.path.exists(fast) else (sys.executable, extra)
    entry = os.path.join(SRC, "launcher", "launcher.py")
    return sys.executable.replace("python.exe", "pythonw.exe"), f'"{entry}" {extra}'


def pinned_dir():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar")


def app_cmd(extra):
    """(exe, args) that starts the Foldy app: the exe when frozen, `pythonw run_foldy.py` during development."""
    if getattr(sys, "frozen", False):
        return sys.executable, extra
    entry = os.path.join(SRC, "run_foldy.py")
    return sys.executable.replace("python.exe", "pythonw.exe"), f'"{entry}" {extra}'


def open_path(p):
    try:
        os.startfile(p)
    except AttributeError:
        subprocess.Popen(["xdg-open", p])


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
        return True
    except Exception:
        return False


def set_autostart(on, exe=None):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                cur, args = app_cmd("--hub")
                winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{exe or cur}" {args}')
            else:
                winreg.DeleteValue(k, APP)
    except Exception:
        pass


def pin_topmost(widget):
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes
    f = ctypes.windll.user32.SetWindowPos
    f.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    f(wintypes.HWND(int(widget.winId())), wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)


def bring_to_front(widget):
    """Really put a window in front and give it keyboard focus. Windows refuses a plain activateWindow() from a tray app
    (the button just flashes), which is why a tray click sometimes seemed to need a second try."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        u.BringWindowToTop.argtypes = [ctypes.c_void_p]
        u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u.IsIconic.argtypes = [ctypes.c_void_p]
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        hwnd = ctypes.c_void_p(int(widget.winId()))
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)                                    # SW_RESTORE
        fg = u.GetForegroundWindow()
        me, other = k.GetCurrentThreadId(), (u.GetWindowThreadProcessId(fg, None) if fg else 0)
        attached = bool(other and other != me and u.AttachThreadInput(me, other, True))
        try:
            u.SetForegroundWindow(hwnd)
            u.BringWindowToTop(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(me, other, False)
    except Exception:
        pass


def dark_titlebar(widget):
    try:
        import ctypes
        v = ctypes.c_int(1)
        for attr in (20, 19):                                   # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old id)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(int(widget.winId())), attr, ctypes.byref(v), 4)
    except Exception:
        pass


def timer_resolution(on):
    """1 ms system timer while animating -> real ~120 Hz instead of Windows' default 15.6 ms ticks."""
    try:
        import ctypes
        (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)
    except Exception:
        pass


def key_down(vk):
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def taskbar_rect():
    """The taskbar window (l, t, r, b, hwnd) in physical px. The bar is on screen at the moment its button is clicked
    (even with auto-hide), so this is always the real thickness, whatever the DPI scale or taskbar size."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.FindWindowW.restype = ctypes.c_void_p
        u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
        hwnd = u.FindWindowW("Shell_TrayWnd", None)
        r = wintypes.RECT()
        if hwnd and u.GetWindowRect(hwnd, ctypes.byref(r)):
            return (r.left, r.top, r.right, r.bottom, hwnd)
    except Exception:
        pass
    return None


_uia = None


def _vcall(ptr, index, restype, argtypes, *args):
    """Call a COM method by vtable slot (no comtypes needed)."""
    import ctypes
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])(ptr, *args)


def _uia_instance():
    global _uia
    if _uia is None:
        _uia = False
        try:
            import ctypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

            def guid(text):
                g = GUID()
                ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(g))
                return g
            clsid = guid("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")           # CUIAutomation
            iid = guid("{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}")             # IUIAutomation
            ptr = ctypes.c_void_p()
            ctypes.oledll.ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(ptr))
            _uia = ptr if ptr.value else False
        except Exception:
            log("UI Automation unavailable:\n" + traceback.format_exc())
    return _uia


def uia_button_rect(px, py, tb):
    """Exact bounding rect (physical px) of the taskbar button under the point, via UI Automation.
    Returns None on any doubt, and the caller falls back to the cursor position."""
    try:
        import ctypes
        from ctypes import wintypes
        uia = _uia_instance()
        if not uia:
            return None
        el = ctypes.c_void_p()
        hr = _vcall(uia, 7, ctypes.c_long, [wintypes.POINT, ctypes.POINTER(ctypes.c_void_p)],      # ElementFromPoint
                    wintypes.POINT(int(px), int(py)), ctypes.byref(el))
        if hr != 0 or not el.value:
            return None
        try:
            pid, tray_pid = ctypes.c_int(), wintypes.DWORD()
            if _vcall(el, 20, ctypes.c_long, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(pid)) != 0:   # CurrentProcessId
                return None
            ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(tb[4]), ctypes.byref(tray_pid))
            if pid.value != tray_pid.value:                          # not the taskbar (and proves the vtable layout is right)
                return None
            r = wintypes.RECT()
            if _vcall(el, 43, ctypes.c_long, [ctypes.POINTER(wintypes.RECT)], ctypes.byref(r)) != 0:   # CurrentBoundingRectangle
                return None
            w, h = r.right - r.left, r.bottom - r.top
            if 16 <= w <= 220 and 16 <= h <= 220 and r.left - 4 <= px <= r.right + 4 and r.top >= tb[1] - 6:
                return (r.left, r.top, r.right, r.bottom)
            return None
        finally:
            _vcall(el, 2, ctypes.c_ulong, [])                         # Release
    except Exception:
        return None


_find_logs = 0
_BTN_CACHE = {}                                  # AppUserModelID (lower) -> last known button rect; survives failed lookups
_FOLDY_ID = re.compile(r"foldy\.[0-9a-f]{10}")
BTN_MIN, BTN_MAX = 16, 220


def _bstr(el, index):
    import ctypes
    b = ctypes.c_void_p()
    if _vcall(el, index, ctypes.c_long, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(b)) != 0 or not b.value:
        return ""
    try:
        return ctypes.wstring_at(b.value)
    finally:
        ctypes.windll.oleaut32.SysFreeString(ctypes.c_void_p(b.value))


def _release(p):
    import ctypes
    if p is not None and p.value:
        _vcall(p, 2, ctypes.c_ulong, [])


def enum_taskbar_buttons(tb):
    """Every button-sized element of the taskbar as dicts {aid, name, cls, rect} (physical px), or None on failure.
    One walk of the UI Automation tree serves every kind of lookup (identity, name, position, cache refresh)."""
    try:
        import ctypes
        from ctypes import wintypes
        uia = _uia_instance()
        if not uia:
            return None
        root, cond, arr = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            if _vcall(uia, 6, ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],        # ElementFromHandle
                      ctypes.c_void_p(tb[4]), ctypes.byref(root)) != 0 or not root.value:
                return None
            pid, tray_pid = ctypes.c_int(), wintypes.DWORD()
            if _vcall(root, 20, ctypes.c_long, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(pid)) != 0:
                return None
            ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(tb[4]), ctypes.byref(tray_pid))
            if pid.value != tray_pid.value:                          # sanity check of the vtable layout
                return None
            if _vcall(uia, 21, ctypes.c_long, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(cond)) != 0:   # CreateTrueCondition
                return None
            if _vcall(root, 6, ctypes.c_long, [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],   # FindAll(Descendants)
                      4, cond, ctypes.byref(arr)) != 0 or not arr.value:
                return None
            count = ctypes.c_int()
            if _vcall(arr, 3, ctypes.c_long, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(count)) != 0:     # get_Length
                return None
            out = []
            for i in range(min(count.value, 800)):
                el = ctypes.c_void_p()
                if _vcall(arr, 4, ctypes.c_long, [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)], i, ctypes.byref(el)) != 0 or not el.value:
                    continue
                try:
                    r = wintypes.RECT()                              # geometry first: cheap way to skip non-buttons
                    if _vcall(el, 43, ctypes.c_long, [ctypes.POINTER(wintypes.RECT)], ctypes.byref(r)) != 0:
                        continue
                    w, h = r.right - r.left, r.bottom - r.top
                    if not (BTN_MIN <= w <= BTN_MAX and BTN_MIN <= h <= BTN_MAX and r.top >= tb[1] - 6):
                        continue
                    out.append({"aid": _bstr(el, 29).lower(), "name": _bstr(el, 23).lower(),       # AutomationId / Name
                                "cls": _bstr(el, 30).lower(),                                       # ClassName
                                "rect": (r.left, r.top, r.right, r.bottom)})
                finally:
                    _release(el)
            return out
        finally:
            _release(arr); _release(cond); _release(root)
    except Exception:
        return None


def _area(b):
    r = b["rect"]
    return (r[2] - r[0]) * (r[3] - r[1])


def task_buttons_in_order(buttons):
    """The buttons Win+1...Win+9 count: app buttons (not Start/Search/tray), left to right, nested duplicates removed."""
    apps = [b for b in buttons if b["aid"].startswith("appid") or "tasklistbutton" in b["cls"]]
    apps.sort(key=lambda b: (b["rect"][0], -_area(b)))
    out = []
    for b in apps:
        if out and b["rect"][0] - out[-1]["rect"][0] < 8:            # same button seen twice (outer + inner element)
            continue
        out.append(b)
    return out


def pick_button(buttons, aumid, name, digit=None):
    """Choose the button for a pinned stack, most reliable evidence first. Pure function (no Windows calls):
       1. its AppUserModelID is in the button's AutomationId       2. Win+<digit> -> the Nth app button on the bar
       3. the button's name is the folder's name                   -> (l, t, r, b) or None"""
    want, base = (aumid or "").lower(), (name or "").lower()
    if want:
        hits = [b for b in buttons if want in b["aid"]]
        if hits:
            return max(hits, key=_area)["rect"]
    if digit:
        order = task_buttons_in_order(buttons)
        n = 9 if digit == 10 else digit - 1                          # Win+0 is the 10th button
        if 0 <= n < len(order):
            return order[n]["rect"]
    if base:
        hits = [b for b in buttons if b["name"] == base or b["name"].startswith(base + " ")]
        if hits:
            return max(hits, key=_area)["rect"]
    return None


def find_button_rect(aumid, name, tb, digit=None):
    """Locate a pinned taskbar button by WHO it is (or by the Win+N number that launched it), not by where the mouse is.
    Falls back to the last position seen for this stack, so a failed lookup never means 'open under the mouse'."""
    global _find_logs
    buttons = enum_taskbar_buttons(tb)
    if buttons:
        for b in buttons:                                            # refresh the cache for every Foldy button on the bar
            m = _FOLDY_ID.search(b["aid"])
            if m:
                _BTN_CACHE[m.group(0)] = b["rect"]
        r = pick_button(buttons, aumid, name, digit)
        if r:
            if aumid:
                _BTN_CACHE[aumid.lower()] = r
            return r
        if _find_logs < 3:                                           # help diagnose Windows builds that name buttons differently
            _find_logs += 1
            log(f"find_button: no match for {aumid!r} / {name!r} / digit {digit}; buttons: "
                + repr([(b['aid'][:40], b['name'][:24], b['cls'][-30:]) for b in buttons[:20]]))
    return _BTN_CACHE.get((aumid or "").lower())


def locate_button(px, py, aumid=None, name=None):
    """Where to open the fan, in logical px: the taskbar's real geometry and the exact button that was used.

    Mouse click: the tracker recorded where it happened, so a fast pointer flick afterwards changes nothing.
    Keyboard (Win+1...): the tracker recorded WHICH number was pressed, and the button is found by its identity, then by
    its position in the taskbar, then from the last position seen. The mouse pointer is only the very last resort."""
    scr = QApplication.primaryScreen()
    dpr, g = scr.devicePixelRatio(), scr.geometry()
    ev = TRACKER.take_event(1.0)
    click = (ev[1], ev[2]) if ev and ev[0] == "click" else None
    digit = ev[1] if ev and ev[0] == "key" else None
    if click:
        px, py = click
    elif px is None:
        pt = QCursor.pos()
        px, py = pt.x() * dpr, pt.y() * dpr
    loc = {"cx": px / dpr, "cy": None if py is None else py / dpr, "tb_top": None, "exact": False}
    tb = taskbar_rect()
    if tb and tb[1] > g.height() * dpr * 0.5 and (tb[3] - tb[1]) < g.height() * dpr * 0.5:     # a bottom taskbar
        loc["tb_top"] = tb[1] / dpr
        r = uia_button_rect(px, py, tb) if (click and py is not None) else None      # the button that was clicked
        if r is not None and aumid:
            _BTN_CACHE[aumid.lower()] = r                            # learn from every click: keyboard launches reuse it
        if r is None:
            r = find_button_rect(aumid, name, tb, digit)             # no click (Win+1...) or lookup failed
        if r is None and py is not None and not click and digit is None:
            r = uia_button_rect(px, py, tb)                          # last resort: the button under the pointer
        if r:
            loc.update(cx=(r[0] + r[2]) / 2 / dpr, cy=(r[1] + r[3]) / 2 / dpr, exact=True)
    return loc


def center_on_screen(w):
    g = QApplication.primaryScreen().availableGeometry()
    w.move(g.center().x() - w.width() // 2, g.center().y() - w.height() // 2)


DIGIT_KEYS = [(n, 0x30 + n) for n in range(1, 10)] + [(10, 0x30)]       # Win+1..Win+9, Win+0 (= 10th button)


class ClickTracker(threading.Thread):
    """Remembers the last primary-button click near the bottom of the screen, and the last Win+<digit> chord.

    A pinned taskbar button starts the launcher ~100 ms after the click or key press, and by then the pointer may be
    elsewhere. This records the event itself, so the fan opens over the button that was really used even if you flick the
    mouse away at once. It samples fast (~250 Hz) while the pointer is in the bottom band of the screen, a button is
    down or the Windows key is held, and ~50 Hz otherwise. No hooks, and it only ever looks at the Win key + digits."""
    BAND = 200                                   # px (physical) from the bottom edge treated as the taskbar area

    def __init__(self):
        super().__init__(daemon=True, name="foldy-click-tracker")
        self.last = None                         # (x, y, monotonic time) of the last click release in the band
        self.key = None                          # (digit 1..10, monotonic time) of the last Win+digit

    def run(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        gas = user32.GetAsyncKeyState
        pt, was_down, held = wintypes.POINT(), False, {}
        screen_h = user32.GetSystemMetrics(1)    # SM_CYSCREEN, physical px (the app is per-monitor DPI aware)
        while True:
            try:
                user32.GetCursorPos(ctypes.byref(pt))
                primary = 0x02 if user32.GetSystemMetrics(23) else 0x01      # honour swapped mouse buttons
                down = bool(gas(primary) & 0x8000)
                in_band = pt.y >= screen_h - self.BAND
                if was_down and not down and in_band:
                    self.last = (pt.x, pt.y, time.monotonic())
                was_down = down
                win = bool(gas(0x5B) & 0x8000 or gas(0x5C) & 0x8000)
                for n, vk in DIGIT_KEYS:                                     # read every digit each round: this also clears stale 'pressed' bits
                    s = gas(vk)
                    if win and ((s & 0x8000 and not held.get(vk)) or s & 1):
                        self.key = (n, time.monotonic())
                    held[vk] = bool(s & 0x8000)
                time.sleep(0.004 if (in_band or down or win) else 0.02)
            except Exception:
                time.sleep(1.0)

    def take(self, max_age=1.5):
        """The recent click as (x, y) in physical px, or None. Consumed, so a later keyboard launch can't reuse it."""
        ev = self.take_event(max_age)
        return (ev[1], ev[2]) if ev and ev[0] == "click" else None

    def take_event(self, max_age=1.5):
        """The newest recent event, consumed: ('click', x, y) or ('key', digit), or None."""
        c, k = self.last, self.key
        self.last = self.key = None
        now = time.monotonic()
        best = None
        if c and now - c[2] <= max_age:
            best = (c[2], ("click", c[0], c[1]))
        if k and now - k[1] <= max_age and (best is None or k[1] > best[0]):
            best = (k[1], ("key", k[0]))
        return best[1] if best else None


TRACKER = ClickTracker()


def start_click_tracker():
    if sys.platform == "win32" and not TRACKER.is_alive():
        TRACKER.start()
