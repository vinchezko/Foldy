"""Foldy.exe entry point.

Pinned taskbar buttons do NOT run this: they run the tiny launcher (src/launcher/launcher.py, built to fsl.exe), which
hands the click to the already-running app. This module decides what a launch of Foldy.exe itself means:

  Foldy.exe                    install (first run from a downloaded copy) / open settings
  Foldy.exe --hub              start hidden (used by "Start with Windows")
  Foldy.exe --folder "C:\\x"   toggle the fan for that folder (used when the launcher has to start the app)
  Foldy.exe --uninstall        open the uninstall confirmation (used by Windows "Apps & features")
"""
import os, subprocess, sys

from .constants import DETACHED, INSTALL_DIR, INSTALL_EXE
from .ipc import send_to_hub


def cursor_xy():
    """Cursor position (physical px), captured the instant we start."""
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.SetProcessDPIAware()
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return None, None


def installed_same(me):
    """True if the installed copy is the very same build (size + timestamp) and its launcher is in place."""
    try:
        a, b = os.stat(me), os.stat(INSTALL_EXE)
        if not (a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)):
            return False
        has_payload = os.path.exists(os.path.join(getattr(sys, "_MEIPASS", ""), "launcher.zip"))
        return (not has_payload) or os.path.exists(os.path.join(INSTALL_DIR, "launcher", "fsl.exe"))
    except OSError:
        return False


def main():
    args = sys.argv[1:]
    if "--px" in args:
        px = int(args[args.index("--px") + 1])
        py = int(args[args.index("--py") + 1]) if "--py" in args else None
    else:
        px, py = cursor_xy()
    folder = args[args.index("--folder") + 1] if "--folder" in args else None
    if folder:
        msg = {"folder": folder, "px": px, "py": py}
    elif "--uninstall" in args:
        msg = {"cmd": "uninstall"}
    elif "--hub" in args:
        msg = {"cmd": "noop"}
    else:
        msg = {"cmd": "home"}

    # A downloaded Foldy.exe (not the installed one): show the installer, or hand over if it is already installed.
    if getattr(sys, "frozen", False) and "--uninstall" not in args:
        if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(INSTALL_EXE):
            if installed_same(sys.executable):
                if not send_to_hub(msg, retries=4):
                    extra = ["--px", str(px), "--py", str(py)] if px is not None and "--px" not in args else []
                    subprocess.Popen([INSTALL_EXE] + args + extra, creationflags=DETACHED, close_fds=True)
                return
            from .installer import run_installer
            run_installer(args, px, py)
            return

    if send_to_hub(msg, retries=4):                           # app already running: hand over and exit
        return
    from .hub import run                                      # otherwise this process becomes the app
    run(msg)
