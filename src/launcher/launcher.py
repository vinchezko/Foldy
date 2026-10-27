"""Foldy launcher (built to fsl.exe) - what pinned taskbar buttons run.

Standard library only, so it starts in ~100 ms. It records where you clicked and hands that to the resident Foldy app
through its named pipe; the app then opens the fan right above that taskbar button. (The app additionally records the
click itself, so this position is only a fallback.)"""
import json
import os
import sys
import time

PIPE = r"\\.\pipe\FoldyHub"


def cursor():
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.SetProcessDPIAware()
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return None, None


def main():
    px, py = cursor()
    args = sys.argv[1:]
    folder = args[args.index("--folder") + 1] if "--folder" in args else None
    msg = {"folder": folder, "px": px, "py": py} if folder else {"cmd": "home"}
    data = (json.dumps(msg) + "\n").encode()
    for _ in range(4):
        try:
            fd = os.open(PIPE, os.O_WRONLY | getattr(os, "O_BINARY", 0))
            os.write(fd, data)
            os.close(fd)
            return
        except FileNotFoundError:
            break                                             # the app isn't running
        except OSError:
            time.sleep(0.03)                                  # pipe busy
    import subprocess                                         # start the app; it opens the fan itself
    if getattr(sys, "frozen", False):                         # ...\Foldy\launcher\fsl.exe -> ...\Foldy\Foldy.exe
        cmd = [os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Foldy.exe")]
    else:
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable.replace("python.exe", "pythonw.exe"), os.path.join(src, "run_foldy.py")]
    extra = ["--px", str(px), "--py", str(py)] if folder and px is not None else []
    subprocess.Popen(cmd + args + extra, creationflags=0x00000008 | 0x08000000, close_fds=True)


if __name__ == "__main__":
    main()
