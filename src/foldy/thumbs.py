"""Real thumbnails for images, videos and PDFs.

Pictures are decoded by Qt (fast, no COM). Videos, PDFs and every other format go through the Windows shell's own
thumbnail provider (IShellItemImageFactory), i.e. exactly what Explorer shows: it uses Explorer's thumbnail cache and the
codecs / PDF handler installed on this PC. Anything without a real thumbnail simply keeps its normal icon.

All decoding happens on one background thread, newest request first, so the fan never waits for a disk or a codec.
The finished picture is framed (rounded corners, hairline border, play badge on videos) on the main thread.
"""
import ctypes, hashlib, os, sys, threading, time
from collections import OrderedDict
from PyQt6.QtCore import QObject, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtCore import QPointF
from .settings import S, log, settings_file


IMAGE_QT = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp"}     # decoded by Qt directly (the plugins we ship)
IMAGE_SHELL = {".gif", ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif", ".svg", ".jxl", ".dng", ".cr2", ".cr3",
               ".nef", ".arw", ".orf", ".rw2", ".raf"}
VIDEO = {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".flv", ".mpg", ".mpeg", ".3gp", ".mts", ".m2ts"}
PDF = {".pdf"}
ALL = IMAGE_QT | IMAGE_SHELL | VIDEO | PDF

REQ = 192                                                       # pixels asked of the decoder (longest side)
CANVAS = 160                                                    # square the framed thumbnail is drawn on


def wants(path, is_dir=False):
    return bool(S.get("thumbs", True)) and not is_dir and os.path.splitext(path)[1].lower() in ALL


# ---------------------------------------------------------------- Windows shell thumbnail provider (ctypes COM)
_shell = None


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", ctypes.c_ushort), ("bmBitsPixel", ctypes.c_ushort),
                ("bmBits", ctypes.c_void_p)]


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


def _guid(s):
    p = s.strip("{}").split("-")
    tail = bytes.fromhex(p[3] + p[4])
    return _GUID(int(p[0], 16), int(p[1], 16), int(p[2], 16), (ctypes.c_ubyte * 8)(*tail))


class _Shell:
    """Loaded once, on the worker thread (COM must be initialised on the thread that uses it)."""
    def __init__(self):
        self.ole = ctypes.WinDLL("ole32")
        self.sh = ctypes.WinDLL("shell32")
        self.gdi = ctypes.WinDLL("gdi32")
        self.usr = ctypes.WinDLL("user32")
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.ole.CoInitializeEx.restype = ctypes.c_long
        self.sh.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(_GUID),
                                                        ctypes.POINTER(ctypes.c_void_p)]
        self.sh.SHCreateItemFromParsingName.restype = ctypes.c_long
        self.gdi.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.gdi.GetObjectW.restype = ctypes.c_int
        self.gdi.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_uint]
        self.gdi.GetDIBits.restype = ctypes.c_int
        self.gdi.DeleteObject.argtypes = [ctypes.c_void_p]
        self.usr.GetDC.argtypes = [ctypes.c_void_p]
        self.usr.GetDC.restype = ctypes.c_void_p
        self.usr.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.ole.CoInitializeEx(None, 2)                          # COINIT_APARTMENTTHREADED (S_FALSE if already done: fine)
        self.iid = _guid("bcc18b79-ba16-442f-80c4-8a59c30c463b")   # IShellItemImageFactory
        self.get_image_t = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
        self.release_t = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)

    def thumbnail(self, path):
        """QImage of the file's real thumbnail, or None when Windows has only a generic icon for it."""
        # THUMBNAILONLY (0x8): fail instead of returning a generic icon. BIGGERSIZEOK (0x1): accept a cached bigger one.
        return self.image(path, REQ, 0x8 | 0x1)

    def image(self, path, size, flags):
        obj = ctypes.c_void_p()
        if self.sh.SHCreateItemFromParsingName(os.path.abspath(path), None, ctypes.byref(self.iid), ctypes.byref(obj)) < 0 or not obj:
            return None
        hbm = ctypes.c_void_p()
        try:
            vt = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            get_image = self.get_image_t(vt[3])
            if get_image(obj, _SIZE(size, size), flags, ctypes.byref(hbm)) < 0 or not hbm:
                return None
            return self._to_image(hbm)
        finally:
            try:
                vt = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
                self.release_t(vt[2])(obj)
            except Exception:
                pass
            if hbm:
                self.gdi.DeleteObject(hbm)

    def _to_image(self, hbm):
        bm = _BITMAP()
        if not self.gdi.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm)) or bm.bmWidth <= 0 or bm.bmHeight <= 0:
            return None
        w, h = bm.bmWidth, abs(bm.bmHeight)
        bmi = _BMIH(ctypes.sizeof(_BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)       # 32-bit, top-down
        buf = ctypes.create_string_buffer(w * h * 4)
        dc = self.usr.GetDC(None)
        try:
            ok = self.gdi.GetDIBits(dc, hbm, 0, h, buf, ctypes.byref(bmi), 0)
        finally:
            self.usr.ReleaseDC(None, dc)
        if not ok:
            return None
        raw = bytes(buf)
        opaque = max(raw[3::4]) == 0                              # no alpha channel in this bitmap: treat as solid
        fmt = QImage.Format.Format_RGB32 if opaque else QImage.Format.Format_ARGB32_Premultiplied
        return QImage(raw, w, h, w * 4, fmt).copy()


def _qt_image(path):
    r = QImageReader(path)
    r.setAutoTransform(True)                                     # honour EXIF rotation
    sz = r.size()
    if sz.isValid() and sz.width() > 0 and sz.height() > 0:
        r.setScaledSize(sz.scaled(REQ, REQ, Qt.AspectRatioMode.KeepAspectRatio))
    img = r.read()
    return None if img.isNull() else img


_main_shell = None


def shell_icon(path, size=128):
    """The file type's icon at full quality (Explorer's 'extra large' icon). Qt's own provider hands back tiny 16-32 px
    icons for many types (scripts, installers...), which then look small and blurry. Runs on the GUI thread."""
    global _main_shell
    if sys.platform != "win32":
        return None
    try:
        if _main_shell is None:
            _main_shell = _Shell()
        img = _main_shell.image(path, size, 0x4)                 # ICONONLY
        return None if img is None else QPixmap.fromImage(img)
    except Exception as ex:
        log(f"thumbs: shell icon failed ({ex!r})")
        return None


# ---------------------------------------------------------------- framing (main thread: QPixmap lives here)
def frame(img, video=False, dpr=1.0):
    """Thumbnail picture -> a square pixmap: the picture fitted inside, rounded, with a hairline border."""
    S_ = int(CANVAS * max(1.0, dpr))
    pm = QPixmap(S_, S_)
    pm.fill(Qt.GlobalColor.transparent)
    sm = img.scaled(S_ - 8, S_ - 8, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    r = QRectF((S_ - sm.width()) / 2, (S_ - sm.height()) / 2, sm.width(), sm.height())
    rad = max(6.0, min(r.width(), r.height()) * 0.07)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath(); clip.addRoundedRect(r, rad, rad)
    p.save(); p.setClipPath(clip); p.drawImage(r, sm); p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 120), 1.6))
    p.drawRoundedRect(r.adjusted(.8, .8, -.8, -.8), rad, rad)
    if video:                                                     # a small play badge so videos read as videos
        d = min(r.width(), r.height()) * 0.36
        c = r.center()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(c, d / 2, d / 2)
        p.setBrush(QColor(255, 255, 255, 235))
        tri = QPolygonF([QPointF(c.x() - d * .13, c.y() - d * .22), QPointF(c.x() - d * .13, c.y() + d * .22),
                         QPointF(c.x() + d * .24, c.y())])
        p.drawPolygon(tri)
    p.end()
    pm.setDevicePixelRatio(1.0)
    return pm


# ---------------------------------------------------------------- the loader
def _disk_dir():
    return os.path.join(os.path.dirname(settings_file()), "thumbs")


def _disk_file(path, mtime):
    try:
        size = os.stat(path).st_size
    except OSError:
        size = 0
    h = hashlib.sha1(f"{os.path.normcase(path)}|{int(mtime or 0)}|{size}".encode("utf-8", "replace")).hexdigest()[:24]
    return os.path.join(_disk_dir(), h + ".png")


def _prune_disk(keep=1500):
    try:
        files = [(e.stat().st_atime, e.path) for e in os.scandir(_disk_dir()) if e.name.endswith(".png")]
        for _, p in sorted(files)[:max(0, len(files) - keep)]:
            os.remove(p)
    except OSError:
        pass


class Thumbs(QObject):
    ready = pyqtSignal(str)                                      # a thumbnail for this path is now in the cache
    WORKERS = 3                                                  # decoded in parallel: one slow video must not hold up the rest

    def __init__(self):
        super().__init__()
        self.cache = OrderedDict()                               # (path, mtime) -> QPixmap | None (None = has no thumbnail)
        self.stack, self.pending = [], set()
        self.cv = threading.Condition()
        self.dpr = 1.0
        self.workers, self.saved = [], 0

    def _key(self, path, mtime):
        return (os.path.normcase(path), int(mtime or 0))

    def peek(self, path, mtime=0):
        """The cached thumbnail pixmap (or None) without queueing anything."""
        return self.cache.get(self._key(path, mtime))

    def fetch(self, path, mtime=0, dpr=1.0):
        """The cached thumbnail pixmap, or None. Looks in memory, then in the thumbnail folder on disk (so a file you
        have seen once shows its picture the instant the fan opens). Otherwise it is queued and `ready` fires later."""
        k = self._key(path, mtime)
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        self.dpr = dpr
        try:
            df = _disk_file(path, mtime)
            if os.path.exists(df):
                img = QImage(df)
                if not img.isNull():
                    pm = frame(img, os.path.splitext(path)[1].lower() in VIDEO, dpr)
                    self._remember(k, pm)
                    return pm
        except Exception as ex:
            log(f"thumbs: disk cache read failed ({ex!r})")
        if k not in self.pending:
            with self.cv:
                self.pending.add(k)
                self.stack.append((k, path, mtime))
                del self.stack[:-300]                           # only the newest requests matter (the user scrolled on)
                self.cv.notify()
            if not self.workers:
                for n in range(self.WORKERS):
                    w = threading.Thread(target=self._run, name=f"foldy-thumbs-{n}", daemon=True)
                    w.start(); self.workers.append(w)
        return None

    def _remember(self, k, pm):
        self.cache[k] = pm
        while len(self.cache) > 250:
            self.cache.popitem(last=False)

    def _run(self):
        shell = None
        if sys.platform == "win32":
            try:
                shell = _Shell()
            except Exception as ex:
                log(f"thumbs: shell provider unavailable ({ex!r})")
        while True:
            with self.cv:
                while not self.stack:
                    self.cv.wait()
                k, path, mtime = self.stack.pop()                # newest first
            img, ext = None, os.path.splitext(path)[1].lower()
            if ext in IMAGE_QT:                                  # pictures Qt can read: fastest, no COM involved
                try:
                    img = _qt_image(path)
                except Exception as ex:
                    log(f"thumbs: Qt could not read {os.path.basename(path)} ({ex!r}); asking Windows instead")
            if img is None and shell is not None:                # everything else (and any picture Qt could not read)
                try:
                    img = shell.thumbnail(path)
                except Exception as ex:
                    log(f"thumbs: Windows gave no thumbnail for {os.path.basename(path)} ({ex!r})")
            if img is not None:
                try:
                    os.makedirs(_disk_dir(), exist_ok=True)
                    img.save(_disk_file(path, mtime), "PNG")
                    self.saved += 1
                    if self.saved % 60 == 0:
                        _prune_disk()
                except Exception:
                    pass
            self._done.emit(k, path, img if img is not None else QImage())

    # worker -> main thread (queued signal, so framing/QPixmap work happens on the GUI thread)
    _done = pyqtSignal(object, str, QImage)

    def start(self):
        self._done.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def _finish(self, k, path, img):
        self.pending.discard(k)
        pm = None
        if not img.isNull():
            try:
                pm = frame(img, os.path.splitext(path)[1].lower() in VIDEO, self.dpr)
            except Exception as ex:
                log(f"thumbs: framing {os.path.basename(path)} failed ({ex!r})")
        self._remember(k, pm)
        if pm is not None:
            self.ready.emit(path)


_thumbs = None


def get():
    """The one loader (created on first use, on the GUI thread)."""
    global _thumbs
    if _thumbs is None:
        _thumbs = Thumbs()
        _thumbs.start()
    return _thumbs
