"""Qt style sheets shared by the settings, install and uninstall windows."""


SETTINGS_QSS = """
QWidget{background:#1d1e23;color:#eceef2;font:13px 'Segoe UI Variable Text','Segoe UI';}
QLabel#title{font-size:24px;font-weight:600;}
QLabel#sub,QLabel#val,QLabel#foot{color:#9aa0ab;}
QLabel#val{min-width:48px;}
QLabel#sec{color:#4cc9ff;font-size:11px;font-weight:600;}
QSlider::groove:horizontal{height:4px;background:#34363e;border-radius:2px;}
QSlider::sub-page:horizontal{background:#4cc9ff;border-radius:2px;}
QSlider::handle:horizontal{background:#ffffff;width:16px;height:16px;margin:-6px 0;border-radius:8px;}
QCheckBox{spacing:10px;}
QCheckBox::indicator{width:18px;height:18px;border-radius:5px;border:1px solid #555a66;background:#262830;}
QCheckBox::indicator:checked{background:#4cc9ff;border-color:#4cc9ff;}
QComboBox{background:#2a2c34;border:1px solid #3d404a;border-radius:8px;padding:6px 10px;min-width:170px;}
QComboBox QAbstractItemView{background:#2a2c34;selection-background-color:#3a3d48;border:1px solid #3d404a;outline:0;}
QPushButton{background:#2f3139;border:1px solid #444855;border-radius:8px;padding:8px 16px;}
QPushButton:hover{background:#3a3d47;}
QPushButton#accent{background:#4cc9ff;color:#0b1a22;border:none;font-weight:600;}
QPushButton#accent:hover{background:#7bd9ff;}
QToolButton#rst{border:none;border-radius:6px;padding:2px 7px;color:#c8ccd6;font-size:16px;background:transparent;}
QToolButton#rst:hover{background:#34363e;color:#ffffff;}
QToolButton#rst:disabled{color:#3a3d46;}
QLabel#title2{font-size:19px;font-weight:600;}
QPushButton#danger{background:#2a1f23;border:1px solid #5a2f36;color:#ff8c98;padding:7px 14px;}
QPushButton#danger:hover{background:#3a252b;color:#ffb0b8;}
QFrame#sep{background:#30323a;max-height:1px;min-height:1px;}
"""


COMPACT_QSS = SETTINGS_QSS + """
QWidget{font:12px 'Segoe UI Variable Text','Segoe UI';}
QLabel{background:transparent;}
QLabel#title{font-size:20px;font-weight:600;}
QLabel#val{min-width:38px;}
QLabel#hint{color:#7d8392;font-size:11px;}
QLabel#note{color:#8fb7cc;font-size:11px;}
QLabel#sec{color:#6e7585;font-size:10px;font-weight:700;letter-spacing:1px;}
QLabel#pill{background:#262830;border:1px solid #3a3d48;border-radius:9px;padding:1px 9px;color:#c8ccd6;font-size:11px;}
QFrame#card{background:#23252d;border:1px solid #2f323b;border-radius:12px;}
QSlider::groove:horizontal{height:5px;background:#363943;border-radius:2px;}
QSlider::sub-page:horizontal{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4cc9ff,stop:1 #808cff);border-radius:2px;}
QSlider::handle:horizontal{background:#ffffff;width:12px;height:12px;margin:-5px 0;border-radius:8px;border:2px solid #4cc9ff;}
QSlider::handle:horizontal:hover{background:#e3f6ff;border-color:#808cff;}
QPushButton{padding:5px 13px;}
QPushButton#ghost{background:transparent;border:1px solid #3d404a;color:#c8ccd6;}
QPushButton#ghost:hover{background:#2c2e37;color:#ffffff;}
QPushButton#update{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3ddc97,stop:1 #4cc9ff);color:#06222e;border:none;font-weight:700;padding:5px 12px;}
QPushButton#update:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6ff0b8,stop:1 #7bd9ff);}
"""


SIDEBAR_QSS = COMPACT_QSS + """
QLabel{background:transparent;}
QFrame#side{background:#16171c;border-right:1px solid #2a2c34;}
QFrame#side QLabel{background:transparent;}
QLabel#title{font-size:19px;font-weight:600;}
QLabel#page{font-size:22px;font-weight:600;}
QLabel#sub{color:#9aa0ab;font-size:12px;}
QLabel#hint2{color:#aab0bc;font-size:12px;}
QLabel#sec{color:#6e7585;font-size:10px;font-weight:700;letter-spacing:1px;}
QLabel#keycap{background:#2a2c34;border:1px solid #3d404a;border-bottom-width:2px;border-radius:6px;padding:1px 8px;color:#e6e8ee;font-size:11px;}
QPushButton#nav{background:transparent;border:none;border-left:3px solid transparent;border-radius:0;text-align:left;padding:11px 18px;color:#a3a9b6;font-size:13px;}
QPushButton#nav:hover{background:#1f2128;color:#ffffff;}
QPushButton#nav:checked{background:#23262f;border-left:3px solid #4cc9ff;color:#ffffff;font-weight:600;}
QFrame#stackrow{background:#23252d;border:1px solid #2f323b;border-radius:12px;}
QFrame#stackrow:hover{background:#262a33;border-color:#4cc9ff;}
QFrame#stackrow QLabel{background:transparent;}
QScrollArea{background:transparent;border:none;}
QScrollArea > QWidget > QWidget{background:transparent;}
QScrollBar:vertical{background:transparent;width:8px;margin:0;}
QScrollBar::handle:vertical{background:#3a3d48;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QPushButton#update{padding:8px 12px;}
QToolButton#rmstack{background:transparent;border:1px solid transparent;border-radius:8px;padding:6px;}
QToolButton#rmstack:hover{background:#3a252b;border-color:#5a2f36;}
QToolButton#cstack{background:transparent;border:1px solid transparent;border-radius:8px;padding:6px;}
QToolButton#cstack:hover{background:#243342;border-color:#3d6e92;}
QMessageBox{background:#1d1e23;}
"""


EDITOR_QSS = SIDEBAR_QSS + """
QDialog{background:#1d1e23;}
QLineEdit{background:#2a2c34;border:1px solid #3d404a;border-radius:8px;padding:6px 10px;selection-background-color:#4cc9ff;selection-color:#06222e;font-size:14px;}
QLineEdit:focus{border-color:#4cc9ff;}
QToolButton#emoji{background:#262830;border:1px solid #333640;border-radius:8px;font:17px 'Segoe UI Emoji','Segoe UI';}
QToolButton#emoji:hover{background:#30333d;border-color:#4cc9ff;}
"""
