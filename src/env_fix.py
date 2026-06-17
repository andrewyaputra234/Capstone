"""Environment fixes applied before heavy dependency imports."""

import os
import sys


def apply_runtime_fixes() -> None:
    """Apply platform fixes before importing aiohttp/crewai and other heavy deps."""
    _fix_ssl_keylog()
    _fix_windows_stdout()


def _fix_ssl_keylog() -> None:
    """Clear SSLKEYLOGFILE when it points at an inaccessible path (common in IDE sandboxes)."""
    keylog = os.environ.get("SSLKEYLOGFILE", "")
    if not keylog:
        return
    blocked = ("Volume{", "virtual_file")
    if any(marker in keylog for marker in blocked):
        os.environ.pop("SSLKEYLOGFILE", None)
        return
    try:
        parent = os.path.dirname(keylog)
        if parent and not os.path.isdir(parent):
            os.environ.pop("SSLKEYLOGFILE", None)
    except OSError:
        os.environ.pop("SSLKEYLOGFILE", None)


def _fix_windows_stdout() -> None:
    """Avoid charmap errors when downstream code prints unicode markers on Windows."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
