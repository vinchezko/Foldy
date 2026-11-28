"""Per-stack icon styles (v1.4.0): colour, text or emoji, and preset textures.

A style is a small dict stored per stack in Documents\\Foldy\\Icons\\styles.json (so it is removed together with the icons
when Foldy is uninstalled):

    {"color": "#RRGGBB" | None,        # None = the automatic hue Foldy always used
     "text":  "AB" | "🎬" | None,      # None = the folder's first letter
     "tcolor": "auto" | "white" | "black",
     "texture": "solid" | "gradient" | "zebra" | ...}

Everything here is drawn in code (no image files). The drawing functions only need QtGui/QtCore, so this module can be
tested without a Windows desktop.
"""
import json, math, os, random, struct
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient


# (key, label, uses your colour?)
TEXTURES = [("solid", "Solid", True), ("gradient", "Gradient", True), ("zebra", "Zebra", False), ("forest", "Forest", False),
            ("ocean", "Ocean", False), ("sunset", "Sunset", False), ("leopard", "Leopard", False), ("carbon", "Carbon", False),
            ("galaxy", "Galaxy", False), ("camo", "Camo", False), ("honey", "Honeycomb", False), ("candy", "Candy", False)]
TEXTURE_KEYS = [k for k, _, _ in TEXTURES]
USES_COLOR = {k for k, _, c in TEXTURES if c}

SWATCHES = ["#ff5c6c", "#ff8a4c", "#ffc247", "#9be15d", "#3ddc97", "#2ec4b6", "#4cc9ff", "#4c8dff", "#808cff", "#a35cff",
            "#e05cff", "#ff5cb8", "#8d6e63", "#78909c", "#37474f", "#f2f2f4"]

EMOJI = ["📁", "📂", "⭐", "❤️", "🔥", "💼", "🎬", "🎵", "🎮", "📷", "📚", "🎓", "💡", "🧪", "🛠️", "💻", "🖼️", "📄", "📦", "☁️", "🏠",
         "✈️", "🛒", "💰", "🎨", "🌿", "🐱", "⚡"]

DEFAULT = {"color": None, "text": None, "tcolor": "auto", "texture": "solid"}

STYLES_NAME = "styles.json"


# ---------------------------------------------------------------- persistence
def _file(icons_dir):
    return os.path.join(icons_dir, STYLES_NAME)


def load_all(icons_dir):
    try:
        with open(_file(icons_dir), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def clean(style):
    """A style dict with only valid keys and values (anything unknown or malformed falls back to the default)."""
    s = dict(DEFAULT)
    if not isinstance(style, dict):
        return s
    c = style.get("color")
    if isinstance(c, str) and QColor(c).isValid():
        s["color"] = QColor(c).name()
    t = style.get("text")
    if isinstance(t, str) and t.strip():
        s["text"] = clip_text(t.strip())
    if style.get("tcolor") in ("auto", "white", "black"):
        s["tcolor"] = style["tcolor"]
    if style.get("texture") in TEXTURE_KEYS:
        s["texture"] = style["texture"]
    return s


def is_default(style):
    return clean(style) == DEFAULT


def get(icons_dir, fid):
    """The saved style of a stack, or None when it was never customised."""
    d = load_all(icons_dir).get(fid)
    if d is None:
        return None
    s = clean(d)
    return None if s == DEFAULT else s


def put(icons_dir, fid, style):
    """Save (or, for a default style, forget) a stack's style."""
    d = load_all(icons_dir)
    s = clean(style)
    if s == DEFAULT:
        d.pop(fid, None)
    else:
        d[fid] = s
    tmp = _file(icons_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _file(icons_dir))


def forget(icons_dir, fid):
    if fid in load_all(icons_dir):
        put(icons_dir, fid, DEFAULT)


# ---------------------------------------------------------------- text helpers
def _graphemes(text):
    """Split into user-perceived characters (pure Python: PyQt6 has no text-boundary finder). An emoji with a skin tone,
    a variation selector or a zero-width joiner sequence, a flag (two regional indicators) and a letter with combining
    marks each count as one."""
    out, cur = [], ""
    for ch in text:
        cp = ord(ch)
        extend = (cp == 0x200D or 0xFE00 <= cp <= 0xFE0F or 0x1F3FB <= cp <= 0x1F3FF or 0x0300 <= cp <= 0x036F
                  or 0xE0020 <= cp <= 0xE007F or cp == 0x20E3)
        flag2 = 0x1F1E6 <= cp <= 0x1F1FF and len(cur) == 1 and 0x1F1E6 <= ord(cur) <= 0x1F1FF
        if cur and (extend or cur[-1] == "\u200d" or flag2):
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    return out


def clip_text(text, n=2):
    """At most `n` user-perceived characters."""
    return "".join(_graphemes(text.strip())[:n])


def is_emoji(text):
    return any(ord(c) >= 0x1F000 or 0x2190 <= ord(c) <= 0x2BFF or ord(c) == 0xFE0F for c in text)


def shown_text(style, folder_name):
    """What is written on the icon."""
    s = style or DEFAULT
    return s.get("text") or (folder_name[:1].upper() if folder_name else "?")


# ---------------------------------------------------------------- colours
def base_color(style, fid):
    """The colour of a solid / gradient icon: the chosen one, or the automatic hue of the folder."""
    c = (style or {}).get("color")
    if c:
        q = QColor(c)
        if q.isValid():
            return q
    return QColor.fromHsv(int(fid[:4], 16) % 360, 170, 235)


def _luma(c):
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def text_colors(style, fid):
    """(fill, outline) for the lettering."""
    s = style or DEFAULT
    mode = s.get("tcolor", "auto")
    tex = s.get("texture", "solid")
    if mode == "auto":
        if tex in USES_COLOR:
            mode = "black" if _luma(base_color(s, fid)) > 190 else "white"
        else:
            mode = "white"
    if mode == "black":
        return QColor(18, 18, 22, 240), QColor(255, 255, 255, 150)
    return QColor(255, 255, 255, 240), QColor(0, 0, 0, 150)


# ---------------------------------------------------------------- textures
# Each one paints onto the rectangle `r` of a painter that is already clipped to the shape being filled. Random parts use
# a fixed seed, so a texture always looks the same.
def _hexpoly(cx, cy, rad):
    return QPolygonF([QPointF(cx + rad * math.cos(math.radians(60 * k + 30)), cy + rad * math.sin(math.radians(60 * k + 30)))
                      for k in range(6)])


def _paint_zebra(p, r):
    p.fillRect(r, QColor(244, 244, 240))
    rnd = random.Random(7)
    w, h = r.width(), r.height()
    n = 9
    step = w * 1.5 / n
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(18, 18, 20))
    for k in range(-5, n):
        x0 = r.left() + k * step
        ph, amp, fr = rnd.uniform(0, 6.28), rnd.uniform(0.05, 0.09) * w, rnd.uniform(2.2, 3.4)
        wid = step * rnd.uniform(0.42, 0.58)
        left, right = [], []
        steps = 28
        for i in range(steps + 1):
            t = i / steps
            y = r.top() + t * h
            cx = x0 + t * w * 0.55 + amp * math.sin(t * fr * math.pi + ph)         # leaning, wavy stripe
            taper = 0.35 + 0.65 * math.sin(math.pi * min(1.0, max(0.0, t * 0.9 + 0.05)))
            ww = wid * taper * (0.75 + 0.25 * math.sin(t * 9 + ph))
            left.append(QPointF(cx - ww / 2, y)); right.append(QPointF(cx + ww / 2, y))
        p.drawPolygon(QPolygonF(left + right[::-1]))


def _paint_forest(p, r):
    w, h = r.width(), r.height()
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor(70, 120, 110)); g.setColorAt(0.55, QColor(38, 84, 62)); g.setColorAt(1, QColor(18, 48, 34))
    p.fillRect(r, g)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 40))
    p.drawEllipse(QPointF(r.left() + w * 0.78, r.top() + h * 0.2), w * 0.09, w * 0.09)                 # a pale moon
    rnd = random.Random(11)
    layers = [(QColor(52, 112, 82), 0.62, 7, 0.34), (QColor(34, 86, 62), 0.76, 8, 0.4), (QColor(16, 52, 38), 0.92, 6, 0.5)]
    for col, base, count, size in layers:
        p.setBrush(col)
        for i in range(count + 1):
            cx = r.left() + (i + rnd.uniform(-0.25, 0.25)) * w / count
            th = h * size * rnd.uniform(0.85, 1.15)
            tw = th * 0.5
            top = r.top() + h * base - th
            for tier in range(3):                                                    # three stacked tiers: a pine
                ty = top + th * tier * 0.28
                tier_w = tw * (0.55 + 0.25 * tier)
                p.drawPolygon(QPolygonF([QPointF(cx, ty), QPointF(cx - tier_w, ty + th * 0.42),
                                         QPointF(cx + tier_w, ty + th * 0.42)]))
        p.drawRect(QRectF(r.left(), r.top() + h * base - 2, w, h))


def _paint_ocean(p, r):
    w, h = r.width(), r.height()
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor(92, 214, 240)); g.setColorAt(0.5, QColor(38, 128, 214)); g.setColorAt(1, QColor(16, 52, 140))
    p.fillRect(r, g)
    p.setPen(Qt.PenStyle.NoPen)
    for k in range(6):
        y0 = r.top() + h * (0.12 + 0.17 * k)
        path = QPainterPath(QPointF(r.left(), r.bottom()))
        path.lineTo(r.left(), y0)
        steps = 40
        for i in range(steps + 1):
            x = r.left() + w * i / steps
            path.lineTo(x, y0 + h * 0.035 * math.sin(i / steps * math.pi * (3 + k % 3) + k * 1.3))
        path.lineTo(r.right(), r.bottom()); path.closeSubpath()
        p.setBrush(QColor(255, 255, 255, 26 + 6 * k)); p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 70), max(1.0, w * 0.006)))
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)


def _paint_sunset(p, r):
    w, h = r.width(), r.height()
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor(88, 60, 170)); g.setColorAt(0.45, QColor(240, 98, 146)); g.setColorAt(0.75, QColor(255, 176, 84))
    g.setColorAt(1, QColor(255, 214, 120))
    p.fillRect(r, g)
    p.setPen(Qt.PenStyle.NoPen)
    sun = QRadialGradient(QPointF(r.center().x(), r.top() + h * 0.62), w * 0.34)
    sun.setColorAt(0, QColor(255, 250, 220, 255)); sun.setColorAt(0.45, QColor(255, 226, 150, 230)); sun.setColorAt(1, QColor(255, 190, 100, 0))
    p.setBrush(sun); p.drawEllipse(QPointF(r.center().x(), r.top() + h * 0.62), w * 0.34, w * 0.34)
    for col, base, amp, ph in ((QColor(120, 54, 120), 0.74, 0.07, 0.0), (QColor(70, 30, 88), 0.86, 0.06, 2.1)):
        path = QPainterPath(QPointF(r.left(), r.bottom()))
        for i in range(41):
            x = r.left() + w * i / 40
            path.lineTo(x, r.top() + h * (base + amp * math.sin(i / 40 * math.pi * 2.2 + ph)))
        path.lineTo(r.right(), r.bottom()); path.closeSubpath()
        p.setBrush(col); p.drawPath(path)


def _paint_leopard(p, r):
    w, h = r.width(), r.height()
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor(238, 176, 68)); g.setColorAt(1, QColor(214, 142, 42))
    p.fillRect(r, g)
    rnd = random.Random(5)
    cell = w / 6.0
    p.setBrush(Qt.BrushStyle.NoBrush)
    rows = int(h / cell) + 2
    for j in range(-1, rows):
        for i in range(-1, 8):
            cx = r.left() + (i + 0.5 + (0.5 if j % 2 else 0) + rnd.uniform(-0.18, 0.18)) * cell
            cy = r.top() + (j + 0.5 + rnd.uniform(-0.18, 0.18)) * cell * 0.92
            rad = cell * rnd.uniform(0.26, 0.36)
            pen = QPen(QColor(54, 32, 18), rad * 0.42)                              # a broken ring: the rosette
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setDashPattern([2.2, 0.9])
            p.setPen(pen)
            start = rnd.randint(0, 360 * 16)
            p.drawArc(QRectF(cx - rad, cy - rad * 0.85, rad * 2, rad * 1.7), start, 300 * 16)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(176, 108, 34, 150))
            p.drawEllipse(QPointF(cx, cy), rad * 0.42, rad * 0.36)
            p.setBrush(Qt.BrushStyle.NoBrush)


def _paint_carbon(p, r):
    p.fillRect(r, QColor(22, 22, 26))
    cell = max(6.0, r.width() / 18.0)
    p.setPen(Qt.PenStyle.NoPen)
    rows, cols = int(r.height() / cell) + 2, int(r.width() / cell) + 2
    for j in range(rows):
        for i in range(cols):
            x, y = r.left() + i * cell, r.top() + j * cell
            horiz = (i + j) % 2 == 0
            g = QLinearGradient(x, y, x + (0 if horiz else cell), y + (cell if horiz else 0))
            g.setColorAt(0, QColor(78, 80, 90)); g.setColorAt(0.5, QColor(34, 35, 40)); g.setColorAt(1, QColor(14, 14, 17))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(x + 0.6, y + 0.6, cell - 1.2, cell - 1.2), cell * 0.2, cell * 0.2)


def _paint_galaxy(p, r):
    w, h = r.width(), r.height()
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(18, 14, 52)); g.setColorAt(1, QColor(40, 14, 70))
    p.fillRect(r, g)
    p.setPen(Qt.PenStyle.NoPen)
    for cx, cy, rad, col in ((0.3, 0.35, 0.55, QColor(130, 80, 255, 120)), (0.72, 0.62, 0.5, QColor(255, 80, 190, 100)),
                             (0.5, 0.85, 0.4, QColor(60, 160, 255, 90))):
        rg = QRadialGradient(QPointF(r.left() + w * cx, r.top() + h * cy), w * rad)
        rg.setColorAt(0, col); rg.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
        p.setBrush(rg); p.drawRect(r)
    rnd = random.Random(3)
    for _ in range(70):
        x, y = r.left() + rnd.random() * w, r.top() + rnd.random() * h
        s = rnd.choice((0.6, 0.9, 1.3)) * max(1.0, w / 120.0)
        p.setBrush(QColor(255, 255, 255, rnd.randint(110, 255)))
        p.drawEllipse(QPointF(x, y), s, s)
    p.setBrush(QColor(255, 255, 255, 230))
    for _ in range(3):                                                              # a few four-point sparkles
        x, y = r.left() + rnd.uniform(0.15, 0.85) * w, r.top() + rnd.uniform(0.15, 0.85) * h
        s = w * 0.05
        p.drawPolygon(QPolygonF([QPointF(x, y - s), QPointF(x + s * 0.2, y - s * 0.2), QPointF(x + s, y), QPointF(x + s * 0.2, y + s * 0.2),
                                 QPointF(x, y + s), QPointF(x - s * 0.2, y + s * 0.2), QPointF(x - s, y), QPointF(x - s * 0.2, y - s * 0.2)]))


def _paint_camo(p, r):
    w, h = r.width(), r.height()
    p.fillRect(r, QColor(104, 116, 58))
    rnd = random.Random(21)
    p.setPen(Qt.PenStyle.NoPen)
    for col, count in ((QColor(150, 134, 84), 16), (QColor(66, 82, 42), 18), (QColor(36, 44, 28), 14)):
        p.setBrush(col)
        for _ in range(count):
            cx, cy = r.left() + rnd.random() * w, r.top() + rnd.random() * h
            p.save()
            p.translate(cx, cy); p.rotate(rnd.uniform(0, 180))
            p.drawEllipse(QPointF(0, 0), w * rnd.uniform(0.09, 0.2), w * rnd.uniform(0.05, 0.1))
            p.restore()


def _paint_honey(p, r):
    w, h = r.width(), r.height()
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor(255, 214, 90)); g.setColorAt(1, QColor(240, 150, 30))
    p.fillRect(r, g)
    rad = max(8.0, w / 7.0)
    dx, dy = rad * math.sqrt(3), rad * 1.5
    pen = QPen(QColor(150, 84, 10, 210), max(1.2, rad * 0.14))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    for j in range(int(h / dy) + 3):
        for i in range(int(w / dx) + 3):
            cx = r.left() + (i - 0.5) * dx + (dx / 2 if j % 2 else 0)
            cy = r.top() + (j - 0.5) * dy
            p.setBrush(QColor(255, 255, 255, 38 if (i + j) % 3 == 0 else 0))
            p.drawPolygon(_hexpoly(cx, cy, rad * 0.98))


def _paint_candy(p, r):
    p.fillRect(r, QColor(255, 244, 246))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 82, 124))
    wid = max(8.0, r.width() / 9.0)
    p.save()
    p.translate(r.center()); p.rotate(-35)
    span = r.width() + r.height()
    k = -span
    while k < span:
        p.drawRect(QRectF(k, -span, wid, span * 2))
        k += wid * 2
    p.restore()


_PAINTERS = {"zebra": _paint_zebra, "forest": _paint_forest, "ocean": _paint_ocean, "sunset": _paint_sunset,
             "leopard": _paint_leopard, "carbon": _paint_carbon, "galaxy": _paint_galaxy, "camo": _paint_camo,
             "honey": _paint_honey, "candy": _paint_candy}


def fill_shape(p, path, rect, style, fid):
    """Fill `path` with the style's colour or texture; `rect` is the area the texture is laid out on."""
    s = style or DEFAULT
    tex = s.get("texture", "solid")
    p.save()
    p.setClipPath(path, Qt.ClipOperation.IntersectClip)
    if tex in _PAINTERS:
        _PAINTERS[tex](p, rect)
    else:
        base = base_color(s, fid)
        g = QLinearGradient(0, rect.top(), 0, rect.bottom())
        if tex == "gradient":
            other = QColor.fromHsv((base.hue() + 48) % 360 if base.hue() >= 0 else 0, min(255, base.saturation() + 10), base.value())
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            g.setColorAt(0, base.lighter(112)); g.setColorAt(1, other.darker(112))
        else:
            g.setColorAt(0, base.lighter(118)); g.setColorAt(1, base)
        p.fillRect(rect, g)
    p.restore()


def _draw_text(p, rect, text, style, fid, px, shadow=True):
    """The lettering: plain on solid colours, outlined on textures (so it reads on stripes and spots), colour emoji as is."""
    s = style or DEFAULT
    if is_emoji(text):
        f = QFont(); f.setFamilies(["Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", "Sans Serif"])
        f.setPixelSize(int(px * (0.95 if len(text) < 2 else 0.62)))
        p.setFont(f); p.setPen(QColor(255, 255, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        return
    fill, outline = text_colors(s, fid)
    f = QFont(); f.setFamilies(["Segoe UI", "Segoe UI Emoji", "Sans Serif"])
    f.setPixelSize(int(px if len(text) < 2 else px * 0.78)); f.setWeight(QFont.Weight.Bold)
    textured = s.get("texture", "solid") not in USES_COLOR
    if textured:
        fm_path = QPainterPath()
        fm_path.addText(0, 0, f, text)
        br = fm_path.boundingRect()
        fm_path.translate(rect.center().x() - br.center().x(), rect.center().y() - br.center().y())
        pen = QPen(outline, px * 0.11)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(fm_path)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(fill); p.drawPath(fm_path)
    else:
        p.setFont(f)
        if shadow:
            p.setPen(QColor(0, 0, 0, 40)); p.drawText(rect.translated(0, px * 0.025), Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(fill); p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


# ---------------------------------------------------------------- the icons
def folder_image(folder_name, fid, style=None, size=256, lettering=True):
    """The taskbar icon: a folder (tab + body) with the style's colour / texture and the lettering on it."""
    s = clean(style) if style else dict(DEFAULT)
    img = QImage(256, 256, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    tab, body = QRectF(22, 46, 108, 60), QRectF(16, 76, 224, 158)
    tab_path, body_path = QPainterPath(), QPainterPath()
    tab_path.addRoundedRect(tab, 16, 16)
    body_path.addRoundedRect(body, 24, 24)
    area = QRectF(16, 46, 224, 188)
    custom = s != DEFAULT
    if s["texture"] in _PAINTERS:
        fill_shape(p, tab_path, area, s, fid)                                       # the tab: the same texture, in shade
        p.fillPath(tab_path, QColor(0, 0, 0, 85))
        fill_shape(p, body_path, area, s, fid)
    else:
        p.setBrush(base_color(s, fid).darker(125)); p.drawPath(tab_path)
        fill_shape(p, body_path, QRectF(16, 70, 224, 164), s, fid)                  # (the v1.3.7 gradient, unchanged)
    if custom:
        hl = QLinearGradient(0, body.top(), 0, body.bottom())                      # a soft light from above
        hl.setColorAt(0, QColor(255, 255, 255, 46)); hl.setColorAt(0.45, QColor(255, 255, 255, 0)); hl.setColorAt(1, QColor(0, 0, 0, 34))
        p.fillPath(body_path, hl)
    if lettering:
        _draw_text(p, body, shown_text(s, folder_name), s, fid, 110, shadow=custom)
    p.end()
    if size != 256:
        img = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return img


def badge_image(folder_name, fid, style=None, size=68):
    """The rounded-square badge shown next to a stack in Settings: same colour, texture and lettering as its icon."""
    s = clean(style) if style else dict(DEFAULT)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(2, 2, size - 4, size - 4)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.235, size * 0.235)
    fill_shape(p, path, rect, s, fid)
    _draw_text(p, rect, shown_text(s, folder_name), s, fid, size * 0.53)
    p.end()
    return img


def ico_bytes(img):
    """A .ico file holding one PNG."""
    ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png = bytes(ba)
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png
