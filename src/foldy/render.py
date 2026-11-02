"""Cached rendering helpers: shell icons, frosted-glass label pills and folder listings."""
import json, os, time
from PyQt6.QtCore import QFileInfo, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from .constants import UNIQUE_EXT
from .settings import S
from . import thumbs


_icon_cache, _label_cache = {}, {}


BAR_KINDS = ("header", "back", "drop", "search")       # the pill-shaped elements (everything that is not a file or folder)


ICONS = None                                   # QFileIconProvider (needs QApplication)


def ui_font(px):
    f = QFont()
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Sans Serif"])
    f.setPixelSize(px); f.setWeight(QFont.Weight.Medium)
    return f


def icon_pixmap(path, is_dir):
    """Shell icon lookups are slow: cache one per extension (or one for all folders)."""
    ext = "" if is_dir else os.path.splitext(path)[1].lower()
    key = "<dir>" if is_dir else (path if ext in UNIQUE_EXT else ext or "<none>")
    pm = _icon_cache.get(key)
    if pm is None:
        pm = thumbs.shell_icon(path)                          # Explorer's large icon (Qt's provider returns tiny ones for some types)
        if pm is None or pm.isNull():
            pm = ICONS.icon(QFileInfo(path)).pixmap(64, 64)
        _icon_cache[key] = pm
    return pm


def glass_label(text, dpr):
    """Frosted dark pill + soft shadow, pre-rendered once. Alpha follows the 'Glass opacity' setting."""
    gl = S["glass"]
    key = (text, dpr, round(gl, 2))
    hit = _label_cache.get(key)
    if hit:
        return hit
    font = ui_font(12)
    fm = QFontMetrics(font)
    t = fm.elidedText(text, Qt.TextElideMode.ElideMiddle, 240)
    w, h, m = fm.horizontalAdvance(t) + 24, 24, 12
    pm = QPixmap(int((w + 2 * m) * dpr), int((h + 2 * m) * dpr))
    pm.setDevicePixelRatio(dpr); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    for k in range(0, m - 3, 2):
        p.setBrush(QColor(0, 0, 0, int((16 * (1 - k / m) + 1) * (0.3 + 0.7 * gl))))
        p.drawRoundedRect(QRectF(m - k, m - k + 2, w + 2 * k, h + 2 * k), 8 + k, 8 + k)
    body = QRectF(m, m, w, h)
    g = QLinearGradient(0, m, 0, m + h)
    g.setColorAt(0, QColor(62, 64, 72, int(255 * gl * 0.92))); g.setColorAt(1, QColor(30, 31, 36, int(255 * gl * 0.95)))
    p.setBrush(g); p.setPen(QPen(QColor(255, 255, 255, int(46 * (0.4 + 0.6 * gl))), 1))
    p.drawRoundedRect(body.adjusted(.5, .5, -.5, -.5), 8, 8)
    p.setFont(font); p.setPen(QColor(245, 245, 247))
    p.drawText(body, Qt.AlignmentFlag.AlignCenter, t)
    p.end()
    if len(_label_cache) > 400:
        _label_cache.clear()
    _label_cache[key] = (pm, w, h, m)
    return _label_cache[key]


def accent_label(text, dpr, hot=False):
    """The blue overlay that floods a drop target (same shape and size as glass_label). Only ever drawn on top of the
    normal glass pill, while a carried file is held over it."""
    key = ("accent", text, dpr, hot)
    hit = _label_cache.get(key)
    if hit:
        return hit
    font = ui_font(12)
    fm = QFontMetrics(font)
    t = fm.elidedText(text, Qt.TextElideMode.ElideMiddle, 240)
    w, h, m = fm.horizontalAdvance(t) + 24, 24, 12
    pm = QPixmap(int((w + 2 * m) * dpr), int((h + 2 * m) * dpr))
    pm.setDevicePixelRatio(dpr); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    for k in range(0, m - 3, 2):
        p.setBrush(QColor(20, 60, 140, int(18 * (1 - k / m) + 2)))
        p.drawRoundedRect(QRectF(m - k, m - k + 2, w + 2 * k, h + 2 * k), 8 + k, 8 + k)
    body = QRectF(m, m, w, h)
    g = QLinearGradient(0, m, 0, m + h)
    if hot:
        g.setColorAt(0, QColor(92, 160, 255, 250)); g.setColorAt(1, QColor(52, 112, 226, 250))
    else:
        g.setColorAt(0, QColor(64, 118, 214, 236)); g.setColorAt(1, QColor(38, 78, 164, 240))
    p.setBrush(g); p.setPen(QPen(QColor(170, 210, 255, 235 if hot else 170), 1.5))
    p.drawRoundedRect(body.adjusted(.75, .75, -.75, -.75), 8, 8)
    p.setFont(font); p.setPen(QColor(255, 255, 255))
    p.drawText(body, Qt.AlignmentFlag.AlignCenter, t)
    p.end()
    if len(_label_cache) > 400:
        _label_cache.clear()
    _label_cache[key] = (pm, w, h, m)
    return _label_cache[key]


# ---------------------------------------------------------------- smart stacks
# A smart stack is a real (nearly empty) folder holding a .foldy-smart.json rule. That way it pins, shows an icon, opens
# and survives updates exactly like any other stack; only its *contents* come from the rule instead of the folder itself.
SMART_FILE = ".foldy-smart.json"
KINDS = {
    "pictures": thumbs.IMAGE_QT | thumbs.IMAGE_SHELL,
    "videos": thumbs.VIDEO,
    "audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus"},
    "documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".ods", ".odp",
                  ".csv", ".md"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".iso"},
}
SKIP_DIRS = {"node_modules", "$recycle.bin", "appdata", "__pycache__", "system volume information", "site-packages"}
_spec_cache, _lnk_cache = {}, {}


def smart_spec(folder):
    """The rule of a smart stack (a dict), or None for an ordinary folder."""
    p = os.path.join(folder, SMART_FILE)
    try:
        m = os.stat(p).st_mtime_ns
    except OSError:
        return None
    hit = _spec_cache.get(p)
    if hit and hit[0] == m:
        return hit[1]
    try:
        with open(p, encoding="utf-8") as f:
            spec = json.load(f)
        spec = spec if isinstance(spec, dict) and spec.get("sources") else None
    except (OSError, ValueError):
        spec = None
    _spec_cache[p] = (m, spec)
    return spec


def recent_dir():
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Microsoft", "Windows", "Recent")


def real_folder(folder):
    """What 'Open in Explorer' should open: a smart stack's first source, any other folder itself."""
    spec = smart_spec(folder)
    if not spec:
        return folder
    for s in spec["sources"]:
        s = recent_dir() if s == "@recent" else s
        if os.path.isdir(s):
            return s
    return folder


def _recent_targets(limit):
    """Files from Windows' own 'Recent' list, newest first: [(time you last opened it, path)]."""
    out = []
    try:
        lnks = sorted(((e.stat().st_mtime, e.path) for e in os.scandir(recent_dir()) if e.name.lower().endswith(".lnk")),
                      reverse=True)[:limit * 4]
    except OSError:
        return out
    pc = None
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        pc = pythoncom
        sh = win32com.client.Dispatch("WScript.Shell")
        for mt, p in lnks:
            hit = _lnk_cache.get(p)
            if hit is None or hit[0] != mt:
                try:
                    hit = _lnk_cache[p] = (mt, sh.CreateShortCut(p).TargetPath)
                except Exception:
                    hit = _lnk_cache[p] = (mt, "")
            if hit[1] and os.path.isfile(hit[1]):
                out.append((mt, hit[1]))
    except Exception:
        pass
    finally:
        if pc is not None:
            pc.CoUninitialize()
    return out


def list_smart(spec, folder):
    """Files for a smart stack: gather from every source, filter by type and age, newest first, keep the first `limit`."""
    now = time.time()
    limit = max(1, min(int(spec.get("limit") or 20), 100))
    days = int(spec.get("days") or 0)
    cutoff = now - days * 86400 if days else 0.0
    exts = KINDS.get(spec.get("kind") or "all")
    depth = 3 if spec.get("recursive") else 0
    deadline, seen, found = time.perf_counter() + 0.6, 0, {}

    def take(mt, path):
        if mt < cutoff or (exts is not None and os.path.splitext(path)[1].lower() not in exts):
            return
        k = os.path.normcase(path)
        if k not in found or found[k][0] < mt:
            found[k] = (mt, os.path.basename(path), path, False)

    for src in spec["sources"]:
        if src == "@recent":
            for mt, p in _recent_targets(limit):
                take(mt, p)
            continue
        todo = [(src, 0)]
        while todo and seen < 60000 and time.perf_counter() < deadline:
            d, lvl = todo.pop()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        seen += 1
                        if e.name.startswith("."):
                            continue
                        try:
                            st = e.stat()
                            if getattr(st, "st_file_attributes", 0) & 0x6:
                                continue
                            if e.is_dir():
                                if lvl < depth and e.name.lower() not in SKIP_DIRS:
                                    todo.append((e.path, lvl + 1))
                            elif e.name.lower() not in ("desktop.ini", "thumbs.db"):
                                take(st.st_mtime, e.path)
                        except OSError:
                            continue
            except OSError:
                continue
    out = sorted(found.values(), reverse=True)[:limit]
    return out or [(0, "Nothing here yet", folder, True)]


def list_entries(folder, sort):
    spec = smart_spec(folder)
    if spec:
        return list_smart(spec, folder)
    out = []
    try:
        with os.scandir(folder) as it:
            for k, e in enumerate(it):
                if k > 4000:
                    break
                if e.name.startswith(".") or e.name.lower() in ("desktop.ini", "thumbs.db"):
                    continue
                try:
                    st = e.stat()
                    isd = e.is_dir()
                except OSError:
                    continue
                if getattr(st, "st_file_attributes", 0) & 0x6:            # hidden | system
                    continue
                out.append((st.st_mtime, e.name, e.path, isd))
    except OSError:
        pass
    if sort == "name":
        out.sort(key=lambda t: t[1].lower())
    elif sort == "folders":
        out.sort(key=lambda t: (not t[3], t[1].lower()))
    else:
        out.sort(reverse=True)                                              # newest first
    return out or [(0, "Folder is empty", folder, True)]


_entries_cache = {}


def entries_for(folder, sort, force=False):
    """list_entries with a short-lived cache keyed on the folder's own timestamp, so re-opening a fan is instant."""
    try:
        m = os.stat(folder).st_mtime
    except OSError:
        m = None
    hit = _entries_cache.get(folder)
    smart = smart_spec(folder) is not None
    if smart and hit and hit[1] == sort and not force:          # smart stacks scan other folders: never make the fan wait
        if time.time() - hit[2] > 3:                            # for it; show the last list and refresh it in the background
            import threading
            threading.Thread(target=refresh_smart, args=(folder,), daemon=True).start()
        return hit[3]
    if hit and hit[0] == m and hit[1] == sort and time.time() - hit[2] < 20 and not smart:
        return hit[3]
    ent = list_entries(folder, sort)
    _entries_cache[folder] = (m, sort, time.time(), ent)
    return ent


_refreshing = set()


def refresh_smart(folder):
    """Re-scan a smart stack (runs on a worker thread) so the next open shows fresh files at once."""
    if folder in _refreshing:
        return
    _refreshing.add(folder)
    try:
        spec = smart_spec(folder)
        if spec:
            _entries_cache[folder] = (None, S["sort"], time.time(), list_smart(spec, folder))
    except Exception:
        pass
    finally:
        _refreshing.discard(folder)


def match_rank(name, q):
    """0 = name starts with the query, 1 = a word in it does, 2 = it appears somewhere inside, None = no match."""
    n = name.lower()
    if n.startswith(q):
        return 0
    i = n.find(q)
    if i < 0:
        return None
    return 1 if (i == 0 or not n[i - 1].isalnum()) else 2


def filter_entries(entries, query, folder):
    """Entries whose name contains the query (case-insensitive), best matches first, the folder's own order kept
    within each group. Nothing found -> a 'No matches' placeholder (same shape as the 'Folder is empty' one)."""
    q = query.strip().lower()
    if not q:
        return entries
    ranked = [(m, k, e) for k, e in enumerate(entries) if (m := match_rank(e[1], q)) is not None]
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [e for _, _, e in ranked] or [(0, "No matches", folder, True)]


class Elt:
    """One fan element: a file/folder item (idx >= 0), the 'Open in Explorer' header or the 'back' pill."""
    def __init__(self, kind, path, name, dpr, is_dir=False, idx=-1, mtime=0):
        self.kind, self.path, self.idx, self.mtime = kind, path, idx, mtime
        self.label, self.lw, self.lh, self.lm = glass_label(name, dpr)
        self.name, self.dpr, self.fillk, self._hot = name, dpr, 0.0, None      # fillk: 0..1, how much of the pill the drop-blue has covered
        self.icon = None if kind in BAR_KINDS else icon_pixmap(path, is_dir)
        self.thumb, self.old_icon, self.thumb_k = None, None, 1.0   # real thumbnail (images / videos / PDFs), the icon it replaced, fade-in 0..1
        self.dummy = False                                          # the 'Folder is empty' / 'No matches' placeholder
        if kind == "item" and thumbs.wants(path, is_dir):
            pm = thumbs.get().fetch(path, mtime, dpr)
            if pm is not None:
                self.icon, self.thumb = pm, pm
        self.nav = False                                            # a folder that can be opened inside the fan
        self.x = self.v = self.target = self.pending = 0.0          # spring state (open progress 0..1)
        self.t_switch = None
        self.hs, self.edge, self.slot = 1.0, 1.0, QPointF()        # hover scale, edge fade, layout position
        self.lv = 1.0 if (kind in BAR_KINDS or S["labels"]) else 0.0  # label visibility (smoothed)

    def set_text(self, text):
        """Re-render the pill with new text (the search pill changes with every key)."""
        self.label, self.lw, self.lh, self.lm = glass_label(text, self.dpr)
        self.name, self._hot = text, None

    def set_thumb(self, pm):
        """A real thumbnail arrived: it fades in over the icon."""
        if pm is None or self.thumb is pm:
            return
        self.old_icon, self.icon, self.thumb, self.thumb_k = self.icon, pm, pm, 0.0

    def hot(self):
        """The same pill in full drop-blue (built on first use)."""
        if self._hot is None:
            self._hot = accent_label(self.name, self.dpr, True)[0]
        return self._hot
