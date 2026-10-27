# PyInstaller spec for the tiny launcher (one folder, so it starts without unpacking anything).
# build.bat packs the result into build/launcher.zip, which is embedded in Foldy.exe and installed next to it.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis([os.path.join(ROOT, "src", "launcher", "launcher.py")],
             excludes=["tkinter", "unittest", "pydoc", "email", "http", "xml", "asyncio", "sqlite3"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fsl",
          icon=os.path.join(ROOT, "assets", "foldy.ico"),
          version=os.path.join(ROOT, "packaging", "version_info.txt"),
          console=False, upx=False, uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="fsl")
