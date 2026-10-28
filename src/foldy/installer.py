"""First-run installer: the steps it performs and the window that shows them."""
import os, shutil, subprocess, sys, time
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QFileIconProvider
from . import render
from .constants import APP, AUTHOR, DETACHED, INSTALL_DIR, INSTALL_EXE, UNINSTALL_KEY, VERSION
from .ipc import send_to_hub
from .shortcuts import _new_link
from .widgets import StepWindow
from .winutil import asset, data_dir, set_autostart, start_menu_lnk


def installer_steps(src):
    """What 'installing' really does. `src` is the exe being run (the downloaded Foldy.exe)."""
    st = os.stat(src)

    def prepare(report):
        report(0.1, "Looking for a running copy…")
        if send_to_hub({"cmd": "quit"}):                            # updating: ask the old version to close
            for n in range(40):
                time.sleep(0.12)
                if not send_to_hub({"cmd": "noop"}):
                    break
                report(0.1 + 0.8 * n / 40, "Closing the old version…")

    def copy(report):
        os.makedirs(INSTALL_DIR, exist_ok=True)
        tmp, total, done = INSTALL_EXE + ".new", st.st_size, 0
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                buf = fi.read(512 * 1024)
                if not buf:
                    break
                fo.write(buf)
                done += len(buf)
                report(done / total, f"Copying… {done / 1048576:.1f} / {total / 1048576:.1f} MB")
        for _ in range(25):
            try:
                os.replace(tmp, INSTALL_EXE)
                break
            except PermissionError:
                time.sleep(0.3)
        else:
            raise OSError("The installed copy is still running and can't be replaced.")
        os.utime(INSTALL_EXE, (st.st_atime, st.st_mtime))          # same timestamp = 'already installed' check works

    def launcher(report):                                           # the tiny launcher that pinned buttons run
        z = asset("launcher.zip")
        if not os.path.exists(z):
            return report(1.0, "No launcher payload (development build)")
        import zipfile
        shutil.rmtree(os.path.join(INSTALL_DIR, "launcher"), ignore_errors=True)
        with zipfile.ZipFile(z) as zf:
            names = zf.namelist()
            for k, n in enumerate(names):
                zf.extract(n, INSTALL_DIR)
                report((k + 1) / len(names), f"Installing launcher… {k + 1}/{len(names)}")

    def docs(report):
        data_dir()

    def start_menu(report):
        import pythoncom
        link = _new_link()
        link.SetPath(INSTALL_EXE); link.SetWorkingDirectory(INSTALL_DIR); link.SetIconLocation(INSTALL_EXE, 0)
        link.SetDescription("Foldy - fan stacks for the Windows taskbar")
        path = start_menu_lnk()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(path, 0)

    def register(report):                                           # shows up in Settings > Apps > Installed apps
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            for name, val in (("DisplayName", "Foldy"), ("DisplayVersion", VERSION), ("Publisher", AUTHOR),
                              ("DisplayIcon", INSTALL_EXE), ("InstallLocation", INSTALL_DIR),
                              ("UninstallString", f'"{INSTALL_EXE}" --uninstall')):
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, int(st.st_size / 1024))

    def autostart(report):
        set_autostart(True, INSTALL_EXE)

    return [("Preparing", 1, prepare), ("Copying Foldy to your PC", 6, copy), ("Installing the fast launcher", 2, launcher),
            ("Creating your Foldy folder in Documents", 1, docs), ("Adding a Start menu shortcut", 1, start_menu),
            ("Registering in Apps & features", 1, register), ("Turning on Start with Windows", 1, autostart)]


def run_installer(args, px=None, py=None):
    """First run of a downloaded Foldy.exe: show an install window with real progress, then start the installed copy."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setWindowIcon(QIcon(asset("foldy.png")))
    render.ICONS = QFileIconProvider()
    steps = installer_steps(sys.executable)
    updating = "--update" in args                                   # started by the in-app updater: swap files, restart quietly
    if updating:
        args = ["--hub"]
    win = StepWindow("Updating Foldy" if updating else "Installing Foldy", [s[0] for s in steps], stop_on_error=True,
                     done_title="Foldy is up to date" if updating else "Foldy is installed", done_sub="Starting Foldy…")

    def done(ok):
        extra = ["--px", str(px), "--py", str(py)] if px is not None and "--px" not in args else []
        subprocess.Popen([INSTALL_EXE] + list(args) + extra, creationflags=DETACHED, close_fds=True)
        app.quit()

    win.show()
    win.begin(steps, done)
    sys.exit(app.exec())
