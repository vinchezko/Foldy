"""Constants shared by the whole app. Standard library only (safe to import without Qt)."""
import os


APP, VERSION = "Foldy", "1.4.0"


AUTHOR, GITHUB = "vinchezko", "https://github.com/vinchezko"


FEEDBACK_URL = "https://forms.gle/ZbeEqztrGYi3z2Wd8"   # Google Form: request a feature, report an issue, ask a question


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


SCROLL_K, SCROLL_C = 230.0, 30.33              # scroll spring: critically damped (zeta = 1) -> glides, never bounces or "ticks"


SCROLL_C_EDGE = 19.0                           # ...and a touch under-damped only while rubber-banding past either end


BUILD_PER_FRAME = 4                            # items a scroll may build in ONE frame (the rest follow on the next frames): no hitch on a fast fling


PREFETCH, KEEP = 3, 8                          # items built ahead of the viewport (a few per frame) / items kept behind it


UNIQUE_EXT = {".exe", ".lnk", ".ico", ".url", ".scr", ".msi", ".appx", ".cur"}
