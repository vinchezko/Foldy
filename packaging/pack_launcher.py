"""Zip dist/fsl -> build/launcher.zip (top folder 'launcher/'); foldy.spec embeds it inside Foldy.exe."""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, DST = os.path.join(ROOT, "dist", "fsl"), os.path.join(ROOT, "build", "launcher.zip")

if not os.path.isdir(SRC):
    sys.exit("dist/fsl not found - build packaging/fsl.spec first")
os.makedirs(os.path.dirname(DST), exist_ok=True)
with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for folder, _, files in os.walk(SRC):
        for name in files:
            full = os.path.join(folder, name)
            z.write(full, os.path.join("launcher", os.path.relpath(full, SRC)))
print(f"packed {DST}: {os.path.getsize(DST) / 1048576:.1f} MB")
