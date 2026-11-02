"""Type-to-filter keyboard capture.

The fan never takes focus (so it can't steal it from your apps), which means Qt never sees key presses. While a fan is
open we therefore install a low-level keyboard hook: printable keys, Backspace, Esc and Enter are routed to the fan
instead of the window that happens to have focus. Ctrl / Alt / Win shortcuts always pass through untouched, and so does
every key while the fan is not listening (closed, folding, carrying a file...).

The hook callback runs on the thread that installed it (the Qt main thread), so the handler may touch Python state
directly; it must stay tiny (Windows drops hooks that answer slowly), so heavy work is scheduled by the caller.
"""
import ctypes, sys
from ctypes import wintypes
from .settings import log


WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
LLKHF_INJECTED = 0x10
VK_BACK, VK_RETURN, VK_ESCAPE, VK_SHIFT, VK_CONTROL, VK_MENU, VK_CAPITAL, VK_LWIN, VK_RWIN = (
    0x08, 0x0D, 0x1B, 0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C)


NAV_KEYS = {0x26: "up", 0x28: "down", 0x25: "left", 0x27: "right", 0x24: "home", 0x23: "end", 0x21: "pgup", 0x22: "pgdn"}
VK_APPS, VK_F10 = 0x5D, 0x79


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


if sys.platform == "win32":
    _LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)           # private copies: never touch the global ctypes.windll prototypes
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    _u32.SetWindowsHookExW.restype = wintypes.HHOOK
    _u32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    _u32.UnhookWindowsHookEx.restype = wintypes.BOOL
    _u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _u32.CallNextHookEx.restype = _LRESULT
    _u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _u32.GetAsyncKeyState.restype = ctypes.c_short
    _u32.GetKeyState.argtypes = [ctypes.c_int]
    _u32.GetKeyState.restype = ctypes.c_short
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _u32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _u32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    _u32.GetKeyboardLayout.restype = wintypes.HKL
    _u32.ToUnicodeEx.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
                                 wintypes.UINT, wintypes.HKL]
    _u32.ToUnicodeEx.restype = ctypes.c_int
    _k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _k32.GetModuleHandleW.restype = wintypes.HMODULE


def _down(vk):
    return bool(_u32.GetAsyncKeyState(vk) & 0x8000)


def _char_for(vk, scan):
    """The character this key press would type right now (layout, Shift and Caps Lock aware), or '' for anything that is
    not a plain printable character (arrows, F-keys, dead keys, shortcuts...)."""
    ctrl, alt = _down(VK_CONTROL), _down(VK_MENU)
    if _down(VK_LWIN) or _down(VK_RWIN) or (ctrl != alt):         # Ctrl+x / Alt+x / Win+x are shortcuts; Ctrl+Alt is AltGr
        return ""
    state = (ctypes.c_ubyte * 256)()
    if _down(VK_SHIFT):
        state[VK_SHIFT] = 0x80
    if _u32.GetKeyState(VK_CAPITAL) & 1:
        state[VK_CAPITAL] = 1
    if ctrl and alt:                                              # AltGr: layouts expect both pressed
        state[VK_CONTROL] = state[VK_MENU] = 0x80
    pid = wintypes.DWORD()
    tid = _u32.GetWindowThreadProcessId(_u32.GetForegroundWindow(), ctypes.byref(pid))
    hkl = _u32.GetKeyboardLayout(tid)
    buf = ctypes.create_unicode_buffer(8)
    n = _u32.ToUnicodeEx(vk, scan, state, buf, 8, 4, hkl)         # flag 4: don't disturb the keyboard's dead-key state
    if n != 1:
        return ""
    ch = buf.value[:1]
    return ch if ch.isprintable() else ""


class KeyHook:
    """handler(kind, value) -> True to swallow the key. gate() is asked first: False = every key passes untouched. kind: 'char' (value = the character), 'back', 'enter' (value 'shift' with Shift), 'esc', 'nav' (value up / down / left /
    right / home / end / pgup / pgdn), 'menu' (context-menu key or Shift+F10).
    handler is only consulted for keys we could possibly want; it decides (by returning False) to let the rest through."""
    def __init__(self, handler, gate=None):
        self.handler, self.gate, self.hook, self._proc, self._eaten = handler, gate or (lambda: True), None, None, set()

    @property
    def active(self):
        return self.hook is not None

    def install(self):
        if self.hook is not None or sys.platform != "win32":
            return self.hook is not None
        try:
            self._proc = HOOKPROC(self._cb)                       # keep a reference: ctypes frees the thunk otherwise
            self.hook = _u32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _k32.GetModuleHandleW(None), 0)
            if not self.hook:
                log(f"keyhook: SetWindowsHookEx failed ({ctypes.get_last_error()})")
                self.hook, self._proc = None, None
        except Exception as ex:
            log(f"keyhook: install failed ({ex!r})")
            self.hook, self._proc = None, None
        return self.hook is not None

    def remove(self):
        h, self.hook = self.hook, None
        self._eaten.clear()
        if h:
            try:
                _u32.UnhookWindowsHookEx(h)
            except Exception:
                pass
        self._proc = None

    def _cb(self, code, wparam, lparam):
        try:
            if code == 0 and self.hook is not None:
                k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (k.flags & LLKHF_INJECTED):                # never touch keys other programs inject
                    vk = k.vkCode
                    if wparam in (WM_KEYUP, WM_SYSKEYUP):
                        if vk in self._eaten:                     # its press was ours: swallow the release too
                            self._eaten.discard(vk)
                            return 1
                    elif wparam in (WM_KEYDOWN, WM_SYSKEYDOWN) and (vk in self._eaten or self.gate()):
                        eat = False
                        if vk in self._eaten:                     # auto-repeat of a key we already took: keep taking it
                            return 1
                        if vk == VK_BACK:
                            eat = self.handler("back", "")
                        elif vk == VK_RETURN:
                            if not (_down(VK_CONTROL) or _down(VK_MENU) or _down(VK_LWIN) or _down(VK_RWIN)):
                                eat = self.handler("enter", "shift" if _down(VK_SHIFT) else "")
                        elif vk in NAV_KEYS or vk == VK_APPS or (vk == VK_F10 and _down(VK_SHIFT)):
                            if not (_down(VK_CONTROL) or _down(VK_MENU) or _down(VK_LWIN) or _down(VK_RWIN)):
                                eat = self.handler("menu", "") if vk in (VK_APPS, VK_F10) else self.handler("nav", NAV_KEYS[vk])
                        elif vk == VK_ESCAPE:
                            eat = self.handler("esc", "")
                        else:
                            ch = _char_for(vk, k.scanCode)
                            if ch:
                                eat = self.handler("char", ch)
                        if eat:
                            self._eaten.add(vk)
                            return 1
        except Exception as ex:                                   # a bug here must never freeze the keyboard
            try:
                log(f"keyhook: handler error {ex!r}")
            except Exception:
                pass
        return _u32.CallNextHookEx(self.hook, code, wparam, lparam)
