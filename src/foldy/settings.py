"""Persistent user settings, runtime flags and the log file."""
import json, os, time


RUNTIME = {"uninstalling": False}               # set while uninstalling so nothing re-creates what we just deleted


DEFAULTS = {"density": 1.0, "speed": 1.0, "glass": 0.9, "magnify": 0.45, "curve": 0.75,
            "maxvis": 14, "sort": "newest", "labels": True, "natural": False, "subfolders": True, "autoupdate": True}


S = dict(DEFAULTS)                             # live settings


def settings_file():
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Foldy", "settings.json")


def load_settings():
    try:
        with open(settings_file(), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return
    for k, v in d.items():
        if k in DEFAULTS:
            try:
                S[k] = type(DEFAULTS[k])(v)
            except Exception:
                pass


def save_settings():
    if RUNTIME["uninstalling"]:
        return
    try:
        os.makedirs(os.path.dirname(settings_file()), exist_ok=True)
        with open(settings_file(), "w", encoding="utf-8") as f:
            json.dump(S, f, indent=1)
    except OSError:
        pass


def log(msg):
    """Append to %APPDATA%\\Foldy\\foldy.log so failures are never silent."""
    if RUNTIME["uninstalling"]:
        return
    try:
        p = os.path.join(os.path.dirname(settings_file()), "foldy.log")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + msg + "\n")
    except OSError:
        pass
