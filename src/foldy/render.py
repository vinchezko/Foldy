"""Cached rendering helpers: shell icons, frosted-glass label pills and folder listings."""
import os, time
from PyQt6.QtCore import QFileInfo, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from .constants import UNIQUE_EXT
from .settings import S


_icon_cache, _label_cache = {}, {}


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
        pm = _icon_cache[key] = ICONS.icon(QFileInfo(path)).pixmap(64, 64)
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


def list_entries(folder, sort):
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


def entries_for(folder, sort):
    """list_entries with a short-lived cache keyed on the folder's own timestamp, so re-opening a fan is instant."""
    try:
        m = os.stat(folder).st_mtime
    except OSError:
        m = None
    hit = _entries_cache.get(folder)
    if hit and hit[0] == m and hit[1] == sort and time.time() - hit[2] < 20:
        return hit[3]
    ent = list_entries(folder, sort)
    _entries_cache[folder] = (m, sort, time.time(), ent)
    return ent


class Elt:
    """One fan element: a file/folder item (idx >= 0), the 'Open in Explorer' header or the 'back' pill."""
    def __init__(self, kind, path, name, dpr, is_dir=False, idx=-1):
        self.kind, self.path, self.idx = kind, path, idx
        self.label, self.lw, self.lh, self.lm = glass_label(name, dpr)
        self.name, self.dpr, self.fillk, self._hot = name, dpr, 0.0, None      # fillk: 0..1, how much of the pill the drop-blue has covered
        self.icon = None if kind in ("header", "back", "drop") else icon_pixmap(path, is_dir)
        self.nav = False                                            # a folder that can be opened inside the fan
        self.x = self.v = self.target = self.pending = 0.0          # spring state (open progress 0..1)
        self.t_switch = None
        self.hs, self.edge, self.slot = 1.0, 1.0, QPointF()        # hover scale, edge fade, layout position
        self.lv = 1.0 if (kind in ("header", "back", "drop") or S["labels"]) else 0.0  # label visibility (smoothed)

    def hot(self):
        """The same pill in full drop-blue (built on first use)."""
        if self._hot is None:
            self._hot = accent_label(self.name, self.dpr, True)[0]
        return self._hot
