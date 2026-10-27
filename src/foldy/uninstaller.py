"""Uninstall confirmation (hold-to-confirm) and the clean-up steps."""
import os, shutil, subprocess, time
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget
from .constants import APP, DETACHED, INSTALL_DIR, INSTALL_EXE, NO_WINDOW, RUN_KEY, UNINSTALL_KEY
from .settings import settings_file
from .shortcuts import lnk_desc
from .styles import SETTINGS_QSS
from .widgets import HoldButton
from .winutil import asset, center_on_screen, dark_titlebar, docs_path, start_menu_lnk


class UninstallConfirm(QWidget):
    """'Do you really wish to uninstall?' with a hold-to-confirm ring button. Non-modal on purpose."""
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.setWindowTitle("Uninstall Foldy")
        self.setWindowIcon(QIcon(asset("foldy.png")))
        self.setStyleSheet(SETTINGS_QSS)
        self.setFixedWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 22)
        root.setSpacing(12)
        title = QLabel("Do you really wish to uninstall Foldy?"); title.setObjectName("title2")
        title.setWordWrap(True); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel("This removes Foldy, its taskbar buttons, shortcuts, settings and startup entry from this PC. "
                      "Windows Explorer will refresh once to clear the taskbar buttons.\n\nYour own folders and files are never touched.")
        body.setObjectName("sub"); body.setWordWrap(True); body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hold = HoldButton()
        self.hold.confirmed.connect(lambda: QTimer.singleShot(450, self.go))
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.close)
        root.addWidget(title); root.addWidget(body); root.addSpacing(4)
        root.addWidget(self.hold, alignment=Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignHCenter)

    def go(self):
        self.close()
        self.hub.begin_uninstall()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
        QTimer.singleShot(0, lambda: center_on_screen(self))


def uninstall_steps():
    """Everything Foldy ever put on this PC. Each step is best-effort: one failure never blocks the rest."""
    st = {"pins": 0}
    pinned_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar")

    def stop(report):
        report(0.5, "Stopping Foldy…")

    def unpin(report):
        try:
            files = [f for f in os.listdir(pinned_dir) if f.lower().endswith(".lnk")]
        except OSError:
            files = []
        d = docs_path()
        mine = {f.lower() for f in os.listdir(d) if f.lower().endswith(".lnk")} if os.path.isdir(d) else set()
        for k, f in enumerate(files):
            fp = os.path.join(pinned_dir, f)
            desc = lnk_desc(fp)
            if (desc is not None and desc.startswith("Foldy stack:")) or (desc is None and f.lower() in mine):
                try:
                    os.remove(fp)
                    st["pins"] += 1
                except OSError:
                    pass
            report((k + 1) / max(1, len(files)), f"Checking taskbar buttons… {k + 1}/{len(files)}")

    def shortcuts(report):
        d = docs_path()
        if os.path.isdir(d):
            lnks = [f for f in os.listdir(d) if f.lower().endswith(".lnk")]
            for k, f in enumerate(lnks):
                try:
                    os.remove(os.path.join(d, f))
                except OSError:
                    pass
                report((k + 1) / max(1, len(lnks)), "Deleting shortcuts…")
            shutil.rmtree(os.path.join(d, "Icons"), ignore_errors=True)
            try:
                os.rmdir(d)                                        # only if nothing else is in there
            except OSError:
                pass
        report(1.0)

    def registry(report):
        import winreg
        try:
            os.remove(start_menu_lnk())
        except OSError:
            pass
        report(0.4, "Cleaning Start menu and startup…")
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, APP)
        except OSError:
            pass
        for kp in (UNINSTALL_KEY, r"Software\Classes\*\shell\taskbarpin"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, kp)
            except OSError:
                pass
        report(1.0)

    def settings(report):
        shutil.rmtree(os.path.dirname(settings_file()), ignore_errors=True)
        report(1.0)

    def taskbar(report):
        if not st["pins"]:
            return report(1.0, "No taskbar buttons to refresh")
        report(0.2, "Refreshing the taskbar…")
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], creationflags=NO_WINDOW, capture_output=True)
        for n in range(40):                                         # Windows restarts Explorer by itself
            time.sleep(0.15)
            out = subprocess.run(["tasklist", "/fi", "imagename eq explorer.exe", "/nh"], creationflags=NO_WINDOW,
                                 capture_output=True, text=True).stdout
            if "explorer.exe" in out.lower():
                break
            report(0.2 + 0.7 * n / 40)
        else:
            subprocess.Popen(["explorer.exe"], creationflags=NO_WINDOW)
        report(1.0)

    def program(report):
        report(0.3, "Removing program files…")
        if os.path.isdir(INSTALL_DIR):                              # a running exe can't delete itself: a detached helper does it after we exit
            subprocess.Popen('cmd.exe /c "ping 127.0.0.1 -n 5 >nul & del /f /q "%s" & rmdir /s /q "%s""' % (INSTALL_EXE, INSTALL_DIR),
                             creationflags=DETACHED, close_fds=True)
        report(1.0)

    return [("Stopping Foldy", 1, stop), ("Removing taskbar buttons", 3, unpin), ("Deleting shortcuts and icons", 2, shortcuts),
            ("Cleaning Start menu, startup and Windows entries", 1, registry), ("Clearing settings and logs", 1, settings),
            ("Refreshing the taskbar", 3, taskbar), ("Removing program files", 1, program)]
