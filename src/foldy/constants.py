"""Constants shared by the whole app. Standard library only (safe to import without Qt)."""
import os


APP, VERSION = "Foldy", "1.2.0"


AUTHOR, GITHUB = "vinchezko", "https://github.com/vinchezko"


REPO, ASSET_NAME = "vinchezko/Foldy", "Foldy.exe"       # where updates are published (a GitHub release with Foldy.exe attached)


PIPE = "FoldyHub"


PIPE_PATH = r"\\.\pipe\FoldyHub"


INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Foldy")


INSTALL_EXE = os.path.join(INSTALL_DIR, "Foldy.exe")


UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Foldy"


DETACHED, NO_WINDOW = 0x00000008 | 0x08000000, 0x08000000


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


WIN_W = 1000                                   # fixed overlay width (never reallocated per open)


BASE_ICON, BASE_SP = 36, 46                    # icon size / arc spacing at 100 % density


K, C_OPEN, C_CLOSE = 300.0, 22.0, 32.0         # open/close spring (open is slightly underdamped = organic)


STAG_OPEN, STAG_CLOSE = 0.018, 0.010           # seconds between successive items


SCROLL_K, SCROLL_C = 140.0, 20.0               # scroll spring (zeta ~0.85: glides, tiny rubber-band overshoot)


UNIQUE_EXT = {".exe", ".lnk", ".ico", ".url", ".scr", ".msi", ".appx", ".cur"}
