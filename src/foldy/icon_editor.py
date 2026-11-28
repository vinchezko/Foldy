"""The 'Customize icon' window (v1.4.0): pick a texture, a colour, and the text or emoji written on a stack's icon.
A live preview shows the real taskbar icon (large, and at the sizes the taskbar uses). Nothing is written until Apply."""
import os
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QToolButton, QVBoxLayout, QWidget)
from . import iconstyle
from .controls import ACCENT, Segmented
from .shortcuts import folder_id, stack_style
from .styles import EDITOR_QSS
from .winutil import dark_titlebar


class Tile(QWidget):
    """One texture: a little folder in that texture, with its name under it."""
    picked = pyqtSignal(str)

    def __init__(self, key, label):
        super().__init__()
        self.key, self.label, self.pm, self.on = key, label, None, False
        self.setFixedSize(84, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    def set_pixmap(self, pm):
        self.pm = pm
        self.update()

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.picked.emit(self.key)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(*ACCENT) if self.on else QColor(47, 50, 59), 2.0 if self.on else 1.0))
        p.setBrush(QColor(38, 42, 52) if self.on else QColor(35, 37, 45))
        p.drawRoundedRect(r, 10, 10)
        if self.pm is not None:
            p.drawPixmap(QRectF((self.width() - 50) / 2, 6, 50, 50), self.pm, QRectF(self.pm.rect()))
        f = QFont(self.font()); f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(236, 238, 242) if self.on else QColor(160, 166, 178))
        p.drawText(QRectF(0, 56, self.width(), 16), int(Qt.AlignmentFlag.AlignCenter), self.label)
        p.end()


class Swatch(QWidget):
    """A round colour chip. kind: 'color' (a fixed colour), 'auto' (Foldy's own hue) or 'custom' (opens the colour dialog)."""
    picked = pyqtSignal(object)

    def __init__(self, kind, hexcolor=None):
        super().__init__()
        self.kind, self.hex, self.on = kind, hexcolor, False
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip({"auto": "Automatic colour", "custom": "Pick any colour…"}.get(kind, hexcolor or ""))

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.update()

    def set_hex(self, hexcolor):
        self.hex = hexcolor
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.picked.emit(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.3)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = QRectF(4, 4, self.width() - 8, self.height() - 8)
        p.setPen(Qt.PenStyle.NoPen)
        if self.kind == "auto":
            g = QConicalGradient(c, 0)
            for k, hue in enumerate((0, 60, 120, 180, 240, 300, 360)):
                g.setColorAt(k / 6.0, QColor.fromHsv(hue % 360, 190, 240))
            p.setBrush(g); p.drawEllipse(r)
        elif self.kind == "custom" and not self.hex:
            p.setPen(QPen(QColor(150, 156, 169), 1.4, Qt.PenStyle.DashLine)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawEllipse(r)
            p.setPen(QPen(QColor(190, 196, 208), 1.6))
            p.drawLine(QPointF(c.x() - 3.5, c.y()), QPointF(c.x() + 3.5, c.y())); p.drawLine(QPointF(c.x(), c.y() - 3.5), QPointF(c.x(), c.y() + 3.5))
        else:
            p.setBrush(QColor(self.hex or "#888888")); p.drawEllipse(r)
        if self.on:
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 235), 2.0))
            p.drawEllipse(QRectF(1.5, 1.5, self.width() - 3, self.height() - 3))
        p.end()


class IconEditor(QDialog):
    """Customise one stack's icon. Open it with IconEditor(hub, folder, parent).show()."""
    def __init__(self, hub, folder, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.hub, self.folder, self.fid = hub, folder, folder_id(folder)
        self.name = os.path.basename(folder.rstrip("\\/")) or folder
        self.style_ = dict(stack_style(self.fid) or iconstyle.DEFAULT)
        self.tile_cache = {}                                     # (texture, colour) -> pixmap of the tile (textures never change)
        self.setWindowTitle("Customize icon")
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())
        self.setStyleSheet(EDITOR_QSS)
        self.setModal(False)
        self.setFixedWidth(600)
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 18); root.setSpacing(12)

        # ---- header: the big preview, and the taskbar sizes
        head = QHBoxLayout(); head.setSpacing(20)
        self.big = QLabel(); self.big.setFixedSize(124, 124)
        col = QVBoxLayout(); col.setSpacing(2)
        title = QLabel("Customize icon"); title.setObjectName("page")
        sub = QLabel(self.name); sub.setObjectName("sub")
        sub.setText(sub.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideMiddle, 340)); sub.setToolTip(folder)
        sizes = QHBoxLayout(); sizes.setSpacing(10)
        self.mid, self.tiny = QLabel(), QLabel()
        self.mid.setFixedSize(40, 40); self.tiny.setFixedSize(24, 24)
        tb = QLabel("On the taskbar"); tb.setObjectName("hint")
        sizes.addWidget(self.mid); sizes.addWidget(self.tiny); sizes.addWidget(tb); sizes.addStretch(1)
        col.addWidget(title); col.addWidget(sub); col.addSpacing(10); col.addLayout(sizes); col.addStretch(1)
        head.addWidget(self.big); head.addLayout(col, 1)
        root.addLayout(head)

        # ---- style tiles
        root.addWidget(self.sec("STYLE"))
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
        self.tiles = []
        for n, (key, label, _uses) in enumerate(iconstyle.TEXTURES):
            t = Tile(key, label)
            t.picked.connect(self.on_texture)
            grid.addWidget(t, n // 6, n % 6)
            self.tiles.append(t)
        root.addLayout(grid)

        # ---- colour
        crow = QHBoxLayout()
        crow.addWidget(self.sec("COLOUR"))
        self.cnote = QLabel("Textures bring their own colours. Pick Solid or Gradient to use yours."); self.cnote.setObjectName("hint")
        crow.addStretch(1); crow.addWidget(self.cnote)
        root.addLayout(crow)
        sw = QHBoxLayout(); sw.setSpacing(6)
        self.swatches = [Swatch("auto")] + [Swatch("color", h) for h in iconstyle.SWATCHES]
        self.custom = Swatch("custom")
        self.swatches.append(self.custom)
        for s in self.swatches:
            s.picked.connect(self.on_swatch)
            sw.addWidget(s)
        sw.addStretch(1)
        root.addLayout(sw)

        # ---- text / emoji
        root.addWidget(self.sec("TEXT OR EMOJI"))
        erow = QHBoxLayout(); erow.setSpacing(12)
        self.edit = QLineEdit(); self.edit.setFixedWidth(120)
        self.edit.setPlaceholderText(iconstyle.shown_text(None, self.name))
        self.edit.textEdited.connect(self.on_text)
        tcl = QLabel("Text colour"); tcl.setObjectName("hint")
        self.tseg = Segmented([("auto", "Auto"), ("white", "White"), ("black", "Dark")])
        self.tseg.setFixedSize(self.tseg.sizeHint())             # never squeezed: the sliding highlight is sized from this
        self.tseg.changed.connect(self.on_tcolor)
        erow.addWidget(self.edit); erow.addStretch(1); erow.addWidget(tcl); erow.addWidget(self.tseg)
        root.addLayout(erow)
        eh = QLabel("Up to 2 characters, or one emoji. Press Win + . for the emoji panel."); eh.setObjectName("hint")
        root.addWidget(eh)
        eg = QGridLayout(); eg.setHorizontalSpacing(6); eg.setVerticalSpacing(6)
        per = 14
        for n, em in enumerate(iconstyle.EMOJI):
            b = QToolButton(); b.setObjectName("emoji"); b.setText(em); b.setFixedSize(34, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, e=em: self.on_emoji(e))
            eg.addWidget(b, n // per, n % per)
        root.addLayout(eg)

        # ---- footer
        root.addSpacing(2)
        self.chk = QCheckBox("Refresh the taskbar now (Explorer restarts for a moment)")
        self.chk.setChecked(True)
        self.chk.setToolTip("Windows only shows a changed taskbar icon after Explorer restarts. Untick to do it yourself later.")
        root.addWidget(self.chk)
        foot = QHBoxLayout(); foot.setSpacing(8)
        reset = QPushButton("Reset to default"); reset.setObjectName("ghost"); reset.clicked.connect(self.reset)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.close)
        ok = QPushButton("Apply"); ok.setObjectName("accent"); ok.clicked.connect(self.apply)
        ok.setDefault(True)
        for b in (reset, cancel, ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        foot.addWidget(reset); foot.addStretch(1); foot.addWidget(cancel); foot.addWidget(ok)
        root.addLayout(foot)

        self.edit.setText(self.style_.get("text") or "")
        self.sync()

    @staticmethod
    def sec(text):
        l = QLabel(text); l.setObjectName("sec")
        return l

    # ---------------------------------------------------------------- state -> widgets
    def dpr(self):
        return max(1.0, self.devicePixelRatioF())

    def pix(self, img, px):
        d = self.dpr()
        pm = QPixmap.fromImage(img.scaled(int(px * d), int(px * d), Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))
        pm.setDevicePixelRatio(d)
        return pm

    def sync(self):
        s = self.style_
        tex = s["texture"]
        uses = tex in iconstyle.USES_COLOR
        for t in self.tiles:
            t.set_on(t.key == tex)
        col = s.get("color")
        known = False
        for sw in self.swatches:
            if sw.kind == "auto":
                sw.set_on(col is None)
            elif sw.kind == "color":
                on = bool(col) and sw.hex.lower() == col.lower()
                known = known or on
                sw.set_on(on)
            sw.setEnabled(uses)
        self.custom.set_hex(col if (col and not known) else None)
        self.custom.set_on(bool(col) and not known)
        self.cnote.setVisible(not uses)
        self.tseg.set_value(s["tcolor"], animate=False)
        self.refresh_tiles()
        self.refresh_preview()

    def refresh_tiles(self):
        col = self.style_.get("color")
        for t in self.tiles:
            key = t.key
            ck = (key, col if key in iconstyle.USES_COLOR else None)
            pm = self.tile_cache.get(ck)
            if pm is None:
                img = iconstyle.folder_image(self.name, self.fid, {"texture": key, "color": ck[1]}, 256, lettering=False)
                pm = self.tile_cache[ck] = self.pix(img, 50)
            t.set_pixmap(pm)

    def refresh_preview(self):
        img = iconstyle.folder_image(self.name, self.fid, self.style_, 256)
        self.big.setPixmap(self.pix(img, 124))
        self.mid.setPixmap(self.pix(img, 40))
        self.tiny.setPixmap(self.pix(img, 24))

    # ---------------------------------------------------------------- user actions
    def on_texture(self, key):
        self.style_["texture"] = key
        self.sync()

    def on_swatch(self, sw):
        if sw.kind == "custom":
            start = QColor(self.style_.get("color") or iconstyle.base_color(None, self.fid).name())
            c = QColorDialog.getColor(start, self, "Pick a colour")
            if not c.isValid():
                return
            self.style_["color"] = c.name()
        elif sw.kind == "auto":
            self.style_["color"] = None
        else:
            self.style_["color"] = sw.hex
        self.sync()

    def on_text(self, text):
        clipped = iconstyle.clip_text(text)
        if clipped != text:
            self.edit.setText(clipped)
        self.style_["text"] = clipped or None
        self.refresh_preview()

    def on_emoji(self, em):
        self.edit.setText(em)
        self.style_["text"] = em
        self.refresh_preview()

    def on_tcolor(self, key):
        self.style_["tcolor"] = key
        self.refresh_preview()

    def reset(self):
        self.style_ = dict(iconstyle.DEFAULT)
        self.edit.clear()
        self.sync()

    def apply(self):
        self.hub.apply_icon_style(self.folder, dict(self.style_), self.chk.isChecked())
        self.close()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)
