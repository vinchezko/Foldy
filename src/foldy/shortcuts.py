"""Per-folder shortcut icons, .lnk creation, taskbar pinning and the native folder picker."""
import hashlib, os, struct, time, traceback
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter
from PyQt6.QtWidgets import QApplication, QWidget
from .settings import log
from .winutil import data_dir, shortcut_cmd


def folder_id(folder):
    return hashlib.md5(os.path.normpath(folder).lower().encode()).hexdigest()[:10]


def make_icon(folder, fid):
    """Per-folder .ico: a coloured folder (hue from the path hash) with the folder's first letter on it."""
    img = QImage(256, 256, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QColor.fromHsv(int(fid[:4], 16) % 360, 170, 235)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(base.darker(125))
    p.drawRoundedRect(QRectF(22, 46, 108, 60), 16, 16)                        # folder tab
    g = QLinearGradient(0, 70, 0, 234)
    g.setColorAt(0, base.lighter(118)); g.setColorAt(1, base)
    p.setBrush(g)
    body = QRectF(16, 76, 224, 158)
    p.drawRoundedRect(body, 24, 24)                                           # folder body
    f = QFont("Segoe UI"); f.setPixelSize(110); f.setWeight(QFont.Weight.Bold)
    p.setFont(f); p.setPen(QColor(255, 255, 255, 235))
    p.drawText(body, Qt.AlignmentFlag.AlignCenter, (os.path.basename(folder.rstrip("\\/")) or folder)[:1].upper())
    p.end()
    ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png = bytes(ba)
    path = os.path.join(data_dir(), "Icons", fid + ".ico")
    with open(path, "wb") as fh:                                              # ICO container holding one PNG
        fh.write(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png)
    return path


def _new_link():
    import pythoncom
    from win32com.shell import shell
    return pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)


def lnk_desc(path):
    try:
        import pythoncom
        l = _new_link()
        l.QueryInterface(pythoncom.IID_IPersistFile).Load(path)
        return l.GetDescription(1024)
    except Exception:
        return None


def migrate_shortcut(path, fast):
    """Older shortcuts ran the big one-file exe (slow start). Point them at the fast launcher, keeping their taskbar ID."""
    import pythoncom
    link = _new_link()
    pf = link.QueryInterface(pythoncom.IID_IPersistFile)
    pf.Load(path, 2)
    target = link.GetPath(0)[0]
    if target.lower().endswith("foldy.exe") and os.path.exists(fast):
        link.SetPath(fast)
        link.SetWorkingDirectory(os.path.dirname(fast))
        pf.Save(path, 0)


def make_shortcut(folder, icon_path):
    """Shortcut in Documents\\Foldy with its own AppUserModelID, so every folder is its own taskbar button."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    fid = folder_id(folder)
    arg = folder + "\\" if folder.endswith("\\") else folder                   # keep drive roots quote-safe
    exe, args = shortcut_cmd(f'--folder "{arg}"')
    base = os.path.basename(folder.rstrip("\\/")) or folder.replace(":", "").replace("\\", "")
    desc = f"Foldy stack: {folder}"
    path = os.path.join(data_dir(), f"{base}.lnk")
    if os.path.exists(path) and lnk_desc(path) != desc:                        # same name, different folder
        path = os.path.join(data_dir(), f"{base} ({fid[:4]}).lnk")
    link = _new_link()
    link.SetPath(exe); link.SetArguments(args); link.SetWorkingDirectory(os.path.dirname(exe))
    link.SetIconLocation(icon_path, 0); link.SetDescription(desc)
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType("Foldy." + fid))
    store.Commit()
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(path, 0)
    return path


def pin_to_taskbar(lnk):
    """Windows has no public pin API. Delegate to Explorer's own 'Pin to taskbar' handler through a temporary verb
    (Windows 10 1809+ and most Windows 11 builds), then fall back to the classic verb if one exists.
    Success is verified by the pin appearing in User Pinned\\TaskBar. Runs on a worker thread, never blocks the UI."""
    import pythoncom, winreg
    from win32com.client import Dispatch
    pinned = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar",
                          os.path.basename(lnk))
    if os.path.exists(pinned):
        return True

    def wait(sec):
        end = time.time() + sec
        while time.time() < end:
            if os.path.exists(pinned):
                return True
            pythoncom.PumpWaitingMessages(); time.sleep(0.04)
        return os.path.exists(pinned)

    try:
        item = Dispatch("Shell.Application").NameSpace(os.path.dirname(lnk)).ParseName(os.path.basename(lnk))
    except Exception:
        log("pin: Shell.Application failed\n" + traceback.format_exc())
        return False
    kp = r"Software\Classes\*\shell\taskbarpin"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, kp) as k:
            winreg.SetValueEx(k, "ExplorerCommandHandler", 0, winreg.REG_SZ, "{90AA3A4E-1CBA-4233-B8BB-535773D48449}")
        item.InvokeVerb("taskbarpin")
        if wait(2.5):
            return True
    except Exception:
        log("pin: handler route failed\n" + traceback.format_exc())
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, kp)
        except OSError:
            pass
    try:
        verbs = item.Verbs()
        for n in range(verbs.Count):
            name = verbs.Item(n).Name.replace("&", "").lower()
            if "pin" in name and "taskbar" in name and "unpin" not in name:
                verbs.Item(n).DoIt()
                if wait(1.5):
                    return True
    except Exception:
        pass
    return False


def pick_folder():
    """Native folder picker on the main thread -> (path, error). Owned by an invisible always-on-top window so it can
    never open behind other apps. It is NOT a Qt-modal dialog, so the fan keeps working while it is open."""
    owner = None
    try:
        import pythoncom
        from win32com.shell import shell, shellcon
        if not (hasattr(shell, "CLSID_FileOpenDialog") and hasattr(shell, "IID_IFileOpenDialog")):
            return "", "this pywin32 has no IFileOpenDialog (Qt's own folder dialog is used instead; harmless)"
        owner = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        c = QApplication.primaryScreen().geometry().center()
        owner.setGeometry(c.x(), c.y(), 1, 1)
        owner.setWindowOpacity(0.01)
        owner.show()
        hwnd = int(owner.winId())
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        except Exception:
            pass
        fod = pythoncom.CoCreateInstance(shell.CLSID_FileOpenDialog, None, pythoncom.CLSCTX_INPROC_SERVER,
                                         shell.IID_IFileOpenDialog)
        fod.SetOptions(fod.GetOptions() | shellcon.FOS_PICKFOLDERS | shellcon.FOS_FORCEFILESYSTEM)
        fod.SetTitle("Pick a folder to pin to the taskbar")
        fod.Show(hwnd)
        return fod.GetResult().GetDisplayName(shellcon.SIGDN_FILESYSPATH), None
    except Exception as ex:
        if ex.args and ex.args[0] == -2147023673:                   # HRESULT 0x800704C7: user cancelled
            return "", None
        return "", repr(ex)
    finally:
        if owner is not None:
            owner.close()


def warm_imports():
    """Import the slow COM modules in the background at startup so the first 'Add folder' is instant."""
    try:
        import win32com.client, win32com.shell.shell, win32com.propsys.propsys  # noqa: F401
    except Exception:
        pass
