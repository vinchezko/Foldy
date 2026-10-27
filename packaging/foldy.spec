# PyInstaller spec -> ONE standalone Foldy.exe (--onefile --noconsole, icon + version info, launcher embedded).
# Run from the repo root (packaging/build.bat does it all):
#   pyinstaller --noconfirm --clean --workpath build/pyi-foldy packaging/foldy.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))          # SPECPATH is provided by PyInstaller


def p(*parts):
    return os.path.join(ROOT, *parts)


LAUNCHER_ZIP = p("build", "launcher.zip")                      # made by packaging/pack_launcher.py
DROP_BINARIES = ("opengl32sw", "d3dcompiler", "qt6pdf", "qt6svg", "qt6quick", "qt6qml",
                 "qsvg", "qpdf", "qtiff", "qwebp", "qgif", "qicns", "qtga", "qwbmp")
APP_MODULES = ["app", "constants", "fan", "hub", "installer", "ipc", "render", "settings", "settings_window",
               "shortcuts", "styles", "uninstaller", "util", "widgets", "winutil"]

a = Analysis(
    [p("src", "run_foldy.py")],
    pathex=[p("src")],
    binaries=[],
    datas=[(p("assets", "foldy.png"), "."), (p("assets", "foldy.ico"), ".")]
          + ([(LAUNCHER_ZIP, ".")] if os.path.exists(LAUNCHER_ZIP) else []),       # fast-launcher payload
    hiddenimports=["foldy." + m for m in APP_MODULES] + [
        "pythoncom", "win32com.client", "win32com.shell.shell", "win32com.shell.shellcon",
        "win32com.propsys.propsys", "win32com.propsys.pscon"],
    excludes=["tkinter", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtSvg", "PyQt6.QtPdf",
              "PyQt6.QtOpenGL", "PyQt6.QtMultimedia", "PyQt6.QtWebEngineCore"],
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not any(x in b[0].lower() for x in DROP_BINARIES)]
a.datas = [d for d in a.datas if "translations" not in d[0].lower()]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Foldy",
    icon=p("assets", "foldy.ico"),
    version=p("packaging", "version_info.txt"),    # publisher / product / copyright shown in Properties -> Details
    console=False,                                 # --noconsole
    upx=False,                                     # UPX raises antivirus false-positives
    uac_admin=False,                               # never asks for admin rights
)
