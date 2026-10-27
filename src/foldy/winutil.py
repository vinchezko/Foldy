"""Windows helpers: paths, autostart, taskbar geometry, UI Automation lookup and the click tracker."""
import os, subprocess, sys, threading, time, traceback
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


def locate_button(px, py):
    """Where to open the fan, in logical px: the taskbar's real geometry and the exact button that was clicked.

    The click position comes from the click tracker (recorded at the instant of the click, so a fast pointer flick
    afterwards changes nothing). Fallbacks: the position the launcher captured, then the current cursor."""
    scr = QApplication.primaryScreen()
    dpr, g = scr.devicePixelRatio(), scr.geometry()
    click = TRACKER.take()
    if click:
        px, py = click
    elif px is None:
        pt = QCursor.pos()
        px, py = pt.x() * dpr, pt.y() * dpr
    loc = {"cx": px / dpr, "cy": None if py is None else py / dpr, "tb_top": None, "exact": False}
    tb = taskbar_rect()
    if tb and tb[1] > g.height() * dpr * 0.5 and (tb[3] - tb[1]) < g.height() * dpr * 0.5:     # a bottom taskbar
        loc["tb_top"] = tb[1] / dpr
        if py is not None:
            r = uia_button_rect(px, py, tb)
            if r:
                loc.update(cx=(r[0] + r[2]) / 2 / dpr, cy=(r[1] + r[3]) / 2 / dpr, exact=True)
    return loc


def center_on_screen(w):
    g = QApplication.primaryScreen().availableGeometry()
    w.move(g.center().x() - w.width() // 2, g.center().y() - w.height() // 2)


class ClickTracker(threading.Thread):
    """Remembers where the primary mouse button was last released near the bottom of the screen, and when.

    A pinned taskbar button starts the launcher ~100 ms after the click, and by then the pointer may be elsewhere.
    This records the click itself, so the fan opens over the button that was really clicked even if you flick the mouse
    away at once. It samples fast (~250 Hz) only while the pointer is in the bottom band of the screen or a button is
    down, and ~25 Hz otherwise. No hooks, no keyboard access."""
    BAND = 200                                   # px (physical) from the bottom edge treated as the taskbar area

    def __init__(self):
        super().__init__(daemon=True, name="foldy-click-tracker")
        self.last = None                         # (x, y, monotonic time) of the last click release in the band

    def run(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pt, was_down = wintypes.POINT(), False
        screen_h = user32.GetSystemMetrics(1)    # SM_CYSCREEN, physical px (the app is per-monitor DPI aware)
        while True:
            try:
                user32.GetCursorPos(ctypes.byref(pt))
                primary = 0x02 if user32.GetSystemMetrics(23) else 0x01      # honour swapped mouse buttons
                down = bool(user32.GetAsyncKeyState(primary) & 0x8000)
                in_band = pt.y >= screen_h - self.BAND
                if was_down and not down and in_band:
                    self.last = (pt.x, pt.y, time.monotonic())
                was_down = down
                time.sleep(0.004 if (in_band or down) else 0.04)
            except Exception:
                time.sleep(1.0)

    def take(self, max_age=1.5):
        """The recent click as (x, y) in physical px, or None. Consumed, so a later keyboard launch can't reuse it."""
        click, self.last = self.last, None
        if click and time.monotonic() - click[2] <= max_age:
            return click[0], click[1]
        return None


TRACKER = ClickTracker()


def start_click_tracker():
    if sys.platform == "win32" and not TRACKER.is_alive():
        TRACKER.start()
