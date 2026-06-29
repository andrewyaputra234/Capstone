"""Environment fixes applied before heavy dependency imports."""

import os
import sys
import asyncio


def apply_runtime_fixes() -> None:
    """Apply platform fixes before importing aiohttp/crewai and other heavy deps."""
    _disable_noisy_local_telemetry()
    _fix_ssl_keylog()
    _fix_windows_stdout()
    _fix_windows_event_loop_policy()


def _disable_noisy_local_telemetry() -> None:
    """Keep optional tracing exporters from timing out during local Streamlit demos."""
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("CREWAI_TELEMETRY_DISABLED", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


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


def _fix_windows_event_loop_policy() -> None:
    """Prefer selector loop on Windows to avoid noisy proactor connection-reset callbacks."""
    if sys.platform != "win32":
        return
    try:
        policy = asyncio.WindowsSelectorEventLoopPolicy()
    except AttributeError:
        return
    try:
        asyncio.set_event_loop_policy(policy)
    except Exception:
        pass
