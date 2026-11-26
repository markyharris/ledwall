"""Git-based update check (standing build rule: 'update available' code).

The hourly check only FLAGS; updating happens when the owner presses
'Update now' on the admin page. Check = git fetch + compare HEAD with
origin/main. Apply = git pull --ff-only; the caller restarts the
service. Outside a git checkout every call degrades gracefully.
"""
import subprocess

from .config import ROOT


def _git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args),
                          capture_output=True, text=True, timeout=60)


def is_checkout():
    try:
        return _git("rev-parse", "--git-dir").returncode == 0
    except Exception:
        return False


def current_version():
    try:
        r = _git("describe", "--tags", "--always", "--dirty")
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "dev"


def check_update():
    """Return {'available': bool|None, 'behind': int|None, 'error': str}."""
    if not is_checkout():
        return {"available": None, "behind": None, "error": "not a git checkout"}
    try:
        f = _git("fetch", "origin", "main")
        if f.returncode != 0:
            return {"available": None, "behind": None,
                    "error": (f.stderr or "fetch failed").strip()[:200]}
        r = _git("rev-list", "--count", "HEAD..origin/main")
        behind = int(r.stdout.strip() or 0)
        return {"available": behind > 0, "behind": behind, "error": ""}
    except Exception as e:
        return {"available": None, "behind": None, "error": str(e)[:200]}


def apply_update():
    """Fast-forward pull. Returns (ok, message)."""
    if not is_checkout():
        return False, "not a git checkout"
    r = _git("pull", "--ff-only", "origin", "main")
    if r.returncode == 0:
        return True, (r.stdout or "updated").strip()[:200]
    return False, (r.stderr or "pull failed").strip()[:200]
