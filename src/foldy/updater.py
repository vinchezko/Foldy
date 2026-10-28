"""Self-update: ask GitHub for the newest release, download its Foldy.exe, check it, and hand it to the installer.

Standard library only. Nothing here runs unless the user allows it: the check can be switched off in Settings, a download
only starts after the user clicks "Update now", and the file must come from this project's own GitHub releases."""
import glob, hashlib, json, os, re, tempfile, urllib.request

from .constants import ASSET_NAME, REPO, VERSION
from .settings import log


API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_PREFIX = f"https://github.com/{REPO}/releases/download/"       # the only place an update may be downloaded from
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def parse_version(text):
    """'v1.2.3-beta' -> (1, 2, 3, 0). Anything unreadable becomes (0, 0, 0, 0), i.e. never newer."""
    nums = [int(n) for n in re.findall(r"\d+", str(text or "").split("-")[0])][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def is_newer(remote, local=VERSION):
    return parse_version(remote) > parse_version(local)


def _open(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": f"Foldy/{VERSION}", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def pick_asset(assets):
    """The release file to install: Foldy.exe, else the first .exe, and only if it lives on this repo's releases."""
    exes = [a for a in assets or [] if str(a.get("name", "")).lower().endswith(".exe")]
    exes.sort(key=lambda a: str(a.get("name", "")).lower() != ASSET_NAME.lower())
    for a in exes:
        if str(a.get("browser_download_url", "")).startswith(RELEASE_PREFIX):
            return a
    return None


def parse_release(data):
    """GitHub 'latest release' JSON -> {version, notes, url, size, sha256, page} or None."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name", "")).lstrip("vV")
    if not version:
        return None
    asset = pick_asset(data.get("assets"))
    digest = str((asset or {}).get("digest") or "")
    return {"version": version, "notes": str(data.get("body") or "").strip()[:700],
            "url": asset["browser_download_url"] if asset else None,
            "size": int(asset.get("size") or 0) if asset else 0,
            "sha256": digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else None,
            "page": data.get("html_url") or RELEASES_PAGE}


def latest_release():
    """(info, ok): info is the newest release dict, ok is False when GitHub couldn't be reached."""
    try:
        with _open(API_LATEST) as r:
            return parse_release(json.loads(r.read().decode("utf-8"))), True
    except Exception as ex:
        log(f"update check failed: {ex!r}")
        return None, False


def download(info, dest, report):
    """Download info['url'] to `dest` (atomically), verifying size and SHA-256 when GitHub provides them."""
    if not info.get("url") or not info["url"].startswith(RELEASE_PREFIX):
        raise OSError("This release has no downloadable Foldy.exe.")
    part, h, got = dest + ".part", hashlib.sha256(), 0
    with _open(info["url"], timeout=30) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        while True:
            buf = r.read(256 * 1024)
            if not buf:
                break
            f.write(buf); h.update(buf); got += len(buf)
            report(got / total if total else 0.0, f"{got / 1048576:.1f} / {total / 1048576:.1f} MB" if total else f"{got / 1048576:.1f} MB")
    if info.get("size") and got != info["size"]:
        os.remove(part)
        raise OSError("The download was incomplete. Please try again.")
    if info.get("sha256") and h.hexdigest() != info["sha256"]:
        os.remove(part)
        raise OSError("The download did not match its checksum, so it was discarded.")
    os.replace(part, dest)


def update_path(version):
    return os.path.join(tempfile.gettempdir(), f"Foldy-{version}-setup.exe")


def cleanup_downloads():
    """Remove update files left in %TEMP% by an earlier update."""
    for f in glob.glob(os.path.join(tempfile.gettempdir(), "Foldy-*-setup.exe*")):
        try:
            os.remove(f)
        except OSError:
            pass
