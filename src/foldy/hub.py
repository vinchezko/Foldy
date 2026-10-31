"""The resident app: tray icon, IPC server, fan control, add/pin flow and uninstall flow."""
import json, os, subprocess, sys, threading, traceback
from PyQt6.QtCore import QObject, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QFileDialog, QFileIconProvider, QMenu, QSystemTrayIcon
from . import dropzone, render, updater
from .constants import APP, AUTHOR, DETACHED, GITHUB, INSTALL_DIR, PIPE, VERSION
from .dragwatch import DragWatch
from .fan import FanOverlay
from .render import _label_cache, entries_for, glass_label, icon_pixmap
from .settings import RUNTIME, S, load_settings, log, save_settings, settings_file
from .settings_window import SettingsWindow
from .shortcuts import (folder_id, lnk_desc, make_icon, make_shortcut, migrate_shortcut, pick_folder,
                        pin_to_taskbar, warm_imports)
from .uninstaller import UninstallConfirm, uninstall_steps
from .update_window import UpdatePrompt
from .widgets import StepWindow
from .winutil import (_BTN_CACHE, asset, bring_to_front, data_dir, docs_path, enum_taskbar_buttons, key_down, locate_button,
                      open_path, pick_button, pinned_dir, set_autostart, start_click_tracker, taskbar_rect)


class Bridge(QObject):
    done = pyqtSignal(str, str, bool, str)       # folder, shortcut, pinned?, error
    stacks = pyqtSignal(list)                    # folders of the pinned stacks
    checked = pyqtSignal(bool, dict, bool)       # update check finished: reached GitHub?, newest release, asked by the user?
    dropped = pyqtSignal(str, str, int, str)     # files dropped on a button: verb, folder, how many were done, error


class Hub:
    def __init__(self, server, first_run):
        self.overlay = FanOverlay()
        self.overlay.on_drop = lambda dest, paths, mods: self.drop_files(dest, paths, mods)
        self.drop_fan = FanOverlay()                                         # opens when a dragged file rests on a pinned button
        self.drop_fan.drop_mode = True
        self.drop_fan.on_drop = self.overlay.on_drop
        self.overlay.on_note = self.drop_fan.on_note = lambda text: self.note(text)
        self.server, self.first_run = server, first_run
        self.settings_win, self.picking = None, False
        self.confirm_win = self.progress_win = None
        self.bridge = Bridge()
        self.bridge.done.connect(self.on_done)
        self.bridge.stacks.connect(self.on_stacks)
        self.bridge.checked.connect(self.on_checked)
        self.bridge.dropped.connect(self.on_dropped)
        self.update_info, self.update_prompt, self.update_win = None, None, None
        self._checking = False
        self._stacks, self._warm_queue = [], []
        self.warm_timer = QTimer(singleShot=True, interval=900)
        self.warm_timer.timeout.connect(self.rewarm)
        server.newConnection.connect(self.on_connect)
        self.save_timer = QTimer(singleShot=True, interval=300)
        self.save_timer.timeout.connect(save_settings)

        self.tray = QSystemTrayIcon(QIcon(asset("foldy.png")))
        m = QMenu()
        m.setWindowFlags(m.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        m.setStyleSheet("""
            QMenu{background:rgba(40,41,46,245);border:1px solid rgba(255,255,255,40);border-radius:10px;padding:6px;}
            QMenu::item{color:#f2f2f4;padding:8px 26px 8px 16px;border-radius:6px;font:13px 'Segoe UI Variable Text','Segoe UI';}
            QMenu::item:selected{background:rgba(255,255,255,28);}
            QMenu::separator{height:1px;background:rgba(255,255,255,30);margin:5px 8px;}""")
        self.act_update = m.addAction("", self.begin_update)             # appears only when an update is waiting
        self.act_update.setVisible(False)
        m.addAction("Settings…", self.open_settings)
        m.addAction("Add folder & pin to taskbar…", self.add_folder)
        m.addAction("Open shortcuts folder", lambda: open_path(data_dir()))
        m.addAction("Copy diagnostics", self.copy_diagnostics)
        m.addSeparator()
        m.addAction(f"by {AUTHOR}", lambda: QDesktopServices.openUrl(QUrl(GITHUB)))
        m.addAction("Quit Foldy", QApplication.quit)
        self.menu = m
        self.tray.setContextMenu(m); self.tray.setToolTip(f"Foldy · by {AUTHOR}")
        self.tray.activated.connect(self.on_tray)                            # one click is enough
        self.tray.show()
        QTimer.singleShot(1000, self.prebuild_settings)                      # build the window ahead of time: the first click is instant
        icon_pixmap(data_dir(), True)                                # warm the folder-icon cache
        threading.Thread(target=warm_imports, daemon=True).start()
        threading.Thread(target=self._scan_stacks, daemon=True).start()
        threading.Thread(target=updater.cleanup_downloads, daemon=True).start()
        self.seed_timer = QTimer(interval=15000)
        self.seed_timer.timeout.connect(self.seed_buttons)
        self.seed_timer.start()
        QTimer.singleShot(5000, self.seed_buttons)
        self.dragwatch = DragWatch(self)                                     # drag a file over a pinned button -> its fan opens
        self.update_timer = QTimer(interval=6 * 3600 * 1000)               # look for a new version every 6 hours
        self.update_timer.timeout.connect(self.auto_check)
        self.update_timer.start()
        QTimer.singleShot(8000, self.auto_check)                            # ...and once shortly after start-up

    def status(self, text):
        if self.settings_win is not None:
            self.settings_win.status.setText(text)

    def note(self, text):
        self.tray.showMessage(APP, text, QSystemTrayIcon.MessageIcon.Information, 5000)

    # ---- IPC
    def on_connect(self):
        s = self.server.nextPendingConnection()
        s.readyRead.connect(lambda s=s: self.on_data(s))
        s.disconnected.connect(s.deleteLater)

    def on_data(self, s):
        for line in bytes(s.readAll()).splitlines():
            try:
                self.handle(json.loads(line))
            except Exception:
                pass

    def handle(self, msg):
        cmd = msg.get("cmd")
        if cmd == "quit":
            return QApplication.quit()
        if cmd == "settings":
            return self.open_settings()
        if cmd == "uninstall":
            return self.open_uninstall()
        if cmd == "add":
            return self.add_folder()
        if cmd == "home":
            return self.add_folder() if self.first_run else self.open_settings()
        f = msg.get("folder")
        if not f or not os.path.isdir(f):
            return
        if msg.get("drop"):                                          # files were dropped onto this stack's taskbar button
            return self.drop_files(f, msg["drop"], int(msg.get("mods") or 0))
        ov = self.overlay
        if folder_id(f) not in self.stack_ids():                     # clicking its button proves it is a stack: drag-in must know it too
            self._stacks.append(f)
            log(f"stack learned from a click: {f}")
        if ov.is_open and ov.root == f:                              # pressing the button again closes it, even inside a sub-folder
            ov.close_fan()
        else:
            name = os.path.basename(f.rstrip("\\/")) or f
            loc = locate_button(msg.get("px"), msg.get("py"), "Foldy." + folder_id(f), name)
            log(f"open: {name}; button located exactly={loc.get('exact')}")
            ov.open_fan(f, loc)

    def copy_diagnostics(self):
        """Put the end of foldy.log on the clipboard, ready to paste into a bug report."""
        try:
            with open(os.path.join(os.path.dirname(settings_file()), "foldy.log"), encoding="utf-8", errors="replace") as f:
                text = "".join(f.readlines()[-80:])
        except OSError:
            text = "(no log yet)"
        QApplication.clipboard().setText(f"Foldy {VERSION}\n" + text)
        self.note("Diagnostics copied. Paste them into the chat.")

    def seed_buttons(self):
        """Remember where every Foldy button sits on the taskbar, so a dragged file reaching one opens its fan at once."""
        try:
            if not self._stacks or self.overlay.is_open or self.drop_fan.is_open or key_down(0x01):
                return
            tb = taskbar_rect()
            if not tb or tb[1] < 100:
                if not getattr(self, "_seed_warned", False):
                    self._seed_warned = True
                    log(f"seed: no bottom taskbar found ({tb})")
                return
            buttons = enum_taskbar_buttons(tb)
            if not buttons:
                if not getattr(self, "_seed_warned2", False):
                    self._seed_warned2 = True
                    log("seed: UI Automation returned no taskbar buttons")
                return
            n = 0
            for fid, f in self.stack_ids().items():
                r = pick_button(buttons, "Foldy." + fid, os.path.basename(f.rstrip("\\/")).lower())
                if r:
                    _BTN_CACHE["foldy." + fid] = r
                    n += 1
            if not getattr(self, "_seed_logged", False):
                self._seed_logged = True
                log(f"seed: found {n} of {len(self._stacks)} Foldy buttons on the taskbar")
        except Exception:
            log(traceback.format_exc())

    def stack_ids(self):
        return {folder_id(f): f for f in self._stacks}

    # ---- files dropped onto a pinned button: move or copy them into that folder
    def drop_files(self, folder, files, mods):
        files = [p for p in files if isinstance(p, str) and os.path.exists(p)]
        if not files:
            return
        verb = dropzone.choose_verb(files, folder, S["dropmode"], mods)
        items = dropzone.usable(files, folder, verb)
        if not items:
            name = os.path.basename(folder.rstrip("\\/")) or folder
            return self.note(f"Already in “{name}”. Hold Ctrl to copy a duplicate.")
        threading.Thread(target=self._drop_worker, args=(folder, items, verb), daemon=True).start()

    def _drop_worker(self, folder, items, verb):
        done, err = 0, ""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                done, err = dropzone.transfer(items, folder, verb)
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            log(traceback.format_exc())
            err = traceback.format_exc().strip().splitlines()[-1]
        self.bridge.dropped.emit(verb, folder, done, err)

    def on_dropped(self, verb, folder, done, err):
        render._entries_cache.pop(folder, None)                      # the folder changed: its fan must be listed again
        self.warm_timer.start()
        if done or err:
            self.note(dropzone.describe(verb, done, folder, err))

    # ---- settings
    def on_tray(self, reason):
        R = QSystemTrayIcon.ActivationReason
        if reason in (R.Trigger, R.DoubleClick):                     # a single click opens; a double click must not toggle it away
            self.open_settings()

    def prebuild_settings(self):
        if self.settings_win is None and not RUNTIME["uninstalling"]:
            self.settings_win = SettingsWindow(self)                 # non-modal: a modal window would block the fan
            if self.update_info:
                self.settings_win.set_update(self.update_info)

    def open_settings(self):
        self.prebuild_settings()
        w = self.settings_win
        w.sync()
        if w.isMinimized():
            w.showNormal()
        w.show(); w.raise_(); w.activateWindow()
        bring_to_front(w)                                            # Windows ignores activateWindow() from a tray app

    def settings_changed(self):
        _label_cache.clear()
        self.overlay.hide_now()
        self.drop_fan.hide_now()
        self.save_timer.start()
        self.warm_timer.start()

    def preview(self):
        folder = os.path.join(os.path.expanduser("~"), "Documents")
        cx = QApplication.primaryScreen().geometry().center().x()
        if self.overlay.is_open:
            self.overlay.close_fan()
        else:
            self.overlay.open_fan(folder, {"cx": cx, "cy": None, "tb_top": None, "exact": False})

    # ---- speed: pre-load icons/labels for every pinned stack, and move old shortcuts onto the fast launcher
    def _scan_stacks(self):
        folders = []
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                fast = os.path.join(INSTALL_DIR, "launcher", "fsl.exe")
                for d in (docs_path(), pinned_dir()):
                    if not os.path.isdir(d):
                        continue
                    for f in os.listdir(d):
                        if not f.lower().endswith(".lnk"):
                            continue
                        path = os.path.join(d, f)
                        desc = lnk_desc(path) or ""
                        if desc.startswith("Foldy stack:"):
                            folders.append(desc.split(":", 1)[1].strip())
                            try:
                                migrate_shortcut(path, fast)
                            except Exception:
                                pass
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            log(traceback.format_exc())
        self.bridge.stacks.emit(sorted(set(folders)))

    def on_stacks(self, folders):
        self._stacks = list(folders)
        self.rewarm()

    def rewarm(self):
        self._warm_queue = list(self._stacks)
        QTimer.singleShot(300, self._warm_next)

    def _warm_next(self):
        if not self._warm_queue or RUNTIME["uninstalling"]:
            return
        folder = self._warm_queue.pop()
        try:
            dpr = QApplication.primaryScreen().devicePixelRatio()
            for _, name, path, isd in entries_for(folder, S["sort"])[:int(S["maxvis"])]:
                icon_pixmap(path, isd)
                glass_label(name, dpr)
            glass_label("Open in Explorer  ↗", dpr)
        except Exception:
            pass
        QTimer.singleShot(60, self._warm_next)

    # ---- updates: ask GitHub, ask the user, download, hand over to the installer
    def auto_check(self):
        if S["autoupdate"] and not RUNTIME["uninstalling"]:
            self.check_updates()

    def check_updates(self, manual=False):
        if self._checking:
            return
        self._checking = True
        if manual:
            self.status("Checking for updates…")
        threading.Thread(target=self._check_worker, args=(manual,), daemon=True).start()

    def _check_worker(self, manual):
        info, ok = updater.latest_release()
        self.bridge.checked.emit(ok, info or {}, manual)

    def on_checked(self, ok, info, manual):
        self._checking = False
        if RUNTIME["uninstalling"]:
            return
        if not ok:
            if manual:
                self.status("Couldn't reach GitHub. Check your internet connection.")
        elif info and updater.is_newer(info["version"]):
            fresh = not self.update_info or self.update_info["version"] != info["version"]
            self.update_info = info
            self.act_update.setText(f"Update to v{info['version']}…")
            self.act_update.setVisible(True)
            self.tray.setToolTip(f"Foldy · update available (v{info['version']})")
            self.prebuild_settings()
            self.settings_win.set_update(info)
            if manual:
                self.status(f"Foldy v{info['version']} is available.")
            if fresh or manual:                                      # ask once per version, or whenever the user asks
                self.show_update_prompt()
        elif manual:
            self.status(f"You're on the latest version (v{VERSION}) ✓")

    def show_update_prompt(self):
        if self.update_info is None:
            return
        if self.update_prompt is not None and self.update_prompt.isVisible():
            self.update_prompt.raise_()
            return
        p = self.update_prompt = UpdatePrompt(self.update_info, can_install=bool(getattr(sys, "frozen", False)))
        p.now.connect(self.begin_update)                             # 'Later' needs no handler: the update button stays in Settings
        p.show(); p.raise_(); p.activateWindow()
        bring_to_front(p)

    def begin_update(self):
        info = self.update_info
        if not info or (self.update_win is not None and self.update_win.isVisible()):
            return
        if not getattr(sys, "frozen", False) or not info.get("url"):  # running from source: just open the release page
            QDesktopServices.openUrl(QUrl(info.get("page") or updater.RELEASES_PAGE))
            return
        dest = updater.update_path(info["version"])

        def download(report):
            updater.download(info, dest, report)

        def verify(report):
            if not os.path.exists(dest) or os.path.getsize(dest) < 1_000_000:
                raise OSError("The downloaded file doesn't look right.")
            report(1.0, "")

        def hand_over(report):                                       # the new exe is an installer: it closes us, swaps files, restarts
            subprocess.Popen([dest, "--update"], creationflags=DETACHED, close_fds=True)
            report(1.0, "Foldy will restart in a moment")

        steps = [(f"Downloading Foldy v{info['version']}", 8, download), ("Checking the download", 1, verify),
                 ("Starting the installer", 1, hand_over)]
        self.update_win = StepWindow(f"Updating Foldy to v{info['version']}", [s[0] for s in steps], accent=(61, 220, 151),
                                     stop_on_error=True, done_title="Almost there", done_sub="Foldy is restarting as the new version…")
        self.update_win.show()
        self.update_win.begin(steps, lambda ok: self.update_win.close())

    # ---- uninstall: hold-to-confirm window -> progress window
    def open_uninstall(self):
        if self.confirm_win is None or not self.confirm_win.isVisible():
            self.confirm_win = UninstallConfirm(self)
        self.confirm_win.show(); self.confirm_win.raise_(); self.confirm_win.activateWindow()

    def begin_uninstall(self):
        RUNTIME["uninstalling"] = True                                         # from now on nothing may write settings/logs again
        self.save_timer.stop()
        self.overlay.hide_now()
        self.drop_fan.hide_now()
        self.tray.hide()
        self.server.close()
        if self.settings_win is not None:
            self.settings_win.hide()
        steps = uninstall_steps()
        self.progress_win = StepWindow("Uninstalling Foldy", [s[0] for s in steps], accent=(255, 92, 108),
                                       stop_on_error=False, done_title="Foldy has been uninstalled",
                                       done_sub="Everything was removed from this PC. Goodbye!")
        self.progress_win.show()
        self.progress_win.begin(steps, lambda ok: QApplication.quit())

    # ---- add + pin
    def add_folder(self):
        if self.picking:
            return
        self.picking = True
        try:
            path, err = pick_folder()
        finally:
            self.picking = False
        if err is not None:                                          # native picker unavailable -> Qt's own dialog
            log("native folder picker failed: " + err)
            path = QFileDialog.getExistingDirectory(None, "Pick a folder to pin to the taskbar", os.path.expanduser("~"))
        self.first_run = False
        if not path:
            return
        d = os.path.normpath(path)
        self.status(f"Adding “{os.path.basename(d.rstrip(chr(92) + '/')) or d}”…")
        try:
            icon = make_icon(d, folder_id(d))                        # tiny; done here, the slow shell work is threaded
        except Exception as ex:
            log(traceback.format_exc())
            return self.note(f"Couldn't create the icon ({ex}).")
        threading.Thread(target=self._pin_worker, args=(d, icon), daemon=True).start()

    def _pin_worker(self, d, icon):
        lnk, pinned, err = "", False, ""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                lnk = make_shortcut(d, icon)
                pinned = pin_to_taskbar(lnk)
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            log(traceback.format_exc())
            err = traceback.format_exc().strip().splitlines()[-1]
        self.bridge.done.emit(d, lnk, pinned, err)

    def on_done(self, d, lnk, pinned, err):
        name = os.path.basename(d.rstrip("\\/")) or d
        if pinned:
            msg = f"Pinned “{name}” to the taskbar. Use the tray icon to add more."
            self._stacks.append(d); self.warm_timer.start()
        elif lnk:
            subprocess.Popen(["explorer", "/select,", lnk])
            msg = "Windows doesn't allow apps to pin automatically any more. Drag the selected shortcut onto your taskbar (or right-click it → Show more options → Pin to taskbar)."
        else:
            msg = f"Couldn't add “{name}”: {err or 'unknown error'} (details: %APPDATA%\\Foldy\\foldy.log)"
        self.status(msg)
        self.note(msg)


def run(msg):
    def _hook(et, ev, tb):                                        # PyQt aborts the whole process on an unhandled error in a slot/event:
        log("".join(traceback.format_exception(et, ev, tb)))      # log it instead, so one bug never takes Foldy down
    sys.excepthook = _hook
    log(f"Foldy {VERSION} starting (build: v1.2.0)")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)                             # tray app: closing settings must not quit
    app.setApplicationName(APP)
    app.setWindowIcon(QIcon(asset("foldy.png")))
    render.ICONS = QFileIconProvider()
    start_click_tracker()
    load_settings()
    QLocalServer.removeServer(PIPE)
    server = QLocalServer()
    if not server.listen(PIPE):                                      # lost a startup race to another hub
        sock = QLocalSocket(); sock.connectToServer(PIPE)
        if sock.waitForConnected(500):
            sock.write(json.dumps(msg).encode() + b"\n"); sock.waitForBytesWritten(500)
        return
    marker = os.path.join(data_dir(), "Icons", ".initialized")
    first = not os.path.exists(marker)
    if first:                                                        # first run: start with Windows so clicks stay instant
        set_autostart(True)
        open(marker, "w").close()
    hub = Hub(server, first)
    QTimer.singleShot(0, lambda: hub.handle(msg))
    sys.exit(app.exec())
