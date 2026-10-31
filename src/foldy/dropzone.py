"""Dropping files onto a pinned button: parse the command line, decide move vs copy, and do the transfer.

Standard library only at import time (the Windows shell module is imported lazily), so the tiny parts of this are safe
to use before Qt is loaded.

How a drop arrives: Windows launches the pinned shortcut's target (fsl.exe) with the dropped paths appended to the
shortcut's arguments:   fsl.exe --folder "C:\\Users\\me\\Downloads" "C:\\a.txt" "D:\\b.png"
"""
import os, shutil

CTRL, SHIFT = 1, 2                                           # modifier bits (held at the moment of the drop)
FLAGS_WITH_VALUE = ("--px", "--py", "--mods")


def current_mods():
    """Ctrl / Shift state right now (Windows only; 0 elsewhere)."""
    try:
        import ctypes
        g = ctypes.windll.user32.GetAsyncKeyState
        return (CTRL if g(0x11) & 0x8000 else 0) | (SHIFT if g(0x10) & 0x8000 else 0)
    except Exception:
        return 0


def drop_args(args):
    """(files, mods) found after `--folder X` on a command line. Files that don't exist are ignored."""
    if "--folder" not in args:
        return [], 0
    rest, files, mods, i = args[args.index("--folder") + 2:], [], None, 0
    while i < len(rest):
        a = rest[i]
        if a in FLAGS_WITH_VALUE:
            if a == "--mods" and i + 1 < len(rest):
                try:
                    mods = int(rest[i + 1])
                except ValueError:
                    pass
            i += 2
            continue
        if not a.startswith("--") and os.path.exists(a):
            files.append(a)
        i += 1
    return files, (mods if mods is not None else (current_mods() if files else 0))


def same_drive(a, b):
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def choose_verb(files, folder, mode, mods):
    """'move' or 'copy'. Ctrl copies and Shift moves (like Explorer); otherwise the Settings choice. 'smart' behaves
    like Explorer: move within one drive, copy across drives."""
    if mods & CTRL:
        return "copy"
    if mods & SHIFT:
        return "move"
    if mode in ("move", "copy"):
        return mode
    return "move" if all(same_drive(f, folder) for f in files) else "copy"


def usable(files, folder, verb):
    """Drop what makes no sense: missing items, the folder itself or one of its parents, and (for moves) items that
    already live in the folder."""
    dest = os.path.normcase(os.path.abspath(folder)).rstrip("\\/")
    out = []
    for f in files:
        if not os.path.exists(f):
            continue
        src = os.path.normcase(os.path.abspath(f)).rstrip("\\/")
        if dest == src or dest.startswith(src + os.sep):
            continue
        if verb == "move" and os.path.dirname(src) == dest:
            continue
        out.append(os.path.abspath(f))
    return out


def unique_path(dst):
    base, ext = os.path.splitext(dst)
    n = 2
    while os.path.exists(dst):
        dst = f"{base} ({n}){ext}"
        n += 1
    return dst


def _fallback(items, folder, verb):
    """Plain shutil transfer (used if the Windows shell route isn't available). Never overwrites: renames instead."""
    done, err = 0, ""
    for src in items:
        dst = unique_path(os.path.join(folder, os.path.basename(src.rstrip("\\/")) or "item"))
        try:
            if verb == "move":
                shutil.move(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            done += 1
        except OSError as ex:
            err = err or str(ex)
    return done, err


def transfer(items, folder, verb):
    """Move/copy items into folder -> (number done, error text). Uses Explorer's own file operation first (progress
    dialog for big jobs, Undo with Ctrl+Z in Explorer, name clashes become "name - Copy"); falls back to shutil."""
    try:
        from win32com.shell import shell, shellcon
    except Exception:
        return _fallback(items, folder, verb)
    flags = shellcon.FOF_ALLOWUNDO | shellcon.FOF_RENAMEONCOLLISION | shellcon.FOF_NOCONFIRMMKDIR
    op = shellcon.FO_MOVE if verb == "move" else shellcon.FO_COPY
    try:
        code, aborted = shell.SHFileOperation((0, op, tuple(items), folder, flags, None, None))
    except Exception:
        return _fallback(items, folder, verb)
    if aborted:
        return 0, ""                                        # the user cancelled in the progress dialog: not an error
    if code:
        return 0, f"Windows reported error {code}"
    return len(items), ""


def describe(verb, n, folder, err=""):
    name = os.path.basename(folder.rstrip("\\/")) or folder
    past = "Moved" if verb == "move" else "Copied"
    what = "1 item" if n == 1 else f"{n} items"
    if err:
        return f"Couldn't {verb} to “{name}”: {err}"
    return f"{past} {what} to “{name}”"


def shell_drag(path):
    """Start a native file drag with the very same data object Explorer uses (what every app, browser and chat window
    expects). Blocks until the drop is over. -> (started, effect or error text). started=False means 'use another way'."""
    try:
        import pythoncom
        from win32com.shell import shell
        item = shell.SHCreateItemFromParsingName(path, None, shell.IID_IShellItem)
        data = item.BindToHandler(None, shell.BHID_DataObject, pythoncom.IID_IDataObject)
        effect = shell.SHDoDragDrop(None, data, None, 1 | 2 | 4)         # copy | move | link
        return True, effect
    except Exception as ex:
        return False, repr(ex)


def native_drag(path, image=None):
    """Explorer-style file drag through the shell (ctypes only), with an optional big drag picture.
    image = (width, height, premultiplied BGRA bytes, hot_x, hot_y). Blocks until the drop is over.
    Raises if the drag could not even start, so the caller can fall back to another way."""
    import ctypes
    from ctypes import wintypes
    ole32, shell32, gdi32 = ctypes.windll.ole32, ctypes.windll.shell32, ctypes.windll.gdi32

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    def guid(text):
        g = GUID()
        if ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g)) != 0:
            raise OSError("bad GUID " + text)
        return g

    def vcall(ptr, index, argtypes, *args):
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])(ptr, *args)

    def release(ptr):
        if ptr is not None and ptr.value:
            vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(ptr)

    class SHDRAGIMAGE(ctypes.Structure):
        _fields_ = [("size", wintypes.SIZE), ("offset", wintypes.POINT), ("bmp", ctypes.c_void_p), ("key", ctypes.c_uint32)]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32), ("biXPels", ctypes.c_int32), ("biYPels", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

    shell32.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
    shell32.SHDoDragDrop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    shell32.SHDoDragDrop.restype = ctypes.c_long
    gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint32]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long

    item, data, helper = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        iid_item = guid("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")          # IShellItem
        if shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(iid_item), ctypes.byref(item)) != 0 or not item.value:
            raise OSError("SHCreateItemFromParsingName failed")
        bhid, iid_do = guid("{B8C0BD9F-ED24-455C-83E6-D5390C4FE8C4}"), guid("{0000010E-0000-0000-C000-000000000046}")
        if vcall(item, 3, [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],   # BindToHandler
                 None, ctypes.byref(bhid), ctypes.byref(iid_do), ctypes.byref(data)) != 0 or not data.value:
            raise OSError("BindToHandler(DataObject) failed")
        if image:
            w, h, bgra, hx, hy = image
            clsid, iid_h = guid("{4657278A-411B-11D2-839A-00C04FD918D0}"), guid("{DE5BF786-477A-11D2-839D-00C04FD918D0}")
            if ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_h), ctypes.byref(helper)) == 0 and helper.value:
                bi, bits = BMIH(40, w, -h, 1, 32, 0, w * h * 4, 0, 0, 0, 0), ctypes.c_void_p()
                hbm = gdi32.CreateDIBSection(None, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
                if hbm and bits.value:
                    ctypes.memmove(bits, bgra, w * h * 4)
                    sd = SHDRAGIMAGE(wintypes.SIZE(w, h), wintypes.POINT(hx, hy), hbm, 0xFFFFFFFF)
                    if vcall(helper, 3, [ctypes.POINTER(SHDRAGIMAGE), ctypes.c_void_p], ctypes.byref(sd), data) != 0:   # InitializeFromBitmap
                        gdi32.DeleteObject(hbm)                                  # (on success the shell owns the bitmap)
        effect = ctypes.c_uint32(0)
        hr = shell32.SHDoDragDrop(None, data, None, 1 | 2 | 4, ctypes.byref(effect))
        if hr < 0:
            raise OSError(f"SHDoDragDrop failed 0x{hr & 0xFFFFFFFF:08X}")
        return effect.value
    finally:
        release(helper); release(data); release(item)
