from functools import cache
import os
from pathlib import Path
import platform
import sys

import rarfile


def _use_unrar(executable):
    previous = rarfile.UNRAR_TOOL
    rarfile.UNRAR_TOOL = str(executable)
    try:
        rarfile.tool_setup(unar=False, bsdtar=False, sevenzip=False, sevenzip2=False, force=True)
    except (rarfile.RarCannotExec, OSError):
        rarfile.UNRAR_TOOL = previous
        return False
    return True


@cache
def configure_unrar():
    """Select a decoder once, from the reader's archive worker."""
    executable = "unrar.exe" if sys.platform == "win32" else "unrar"
    for directory in os.get_exec_path():
        candidate = Path(directory.strip('"')) / executable
        if candidate.is_absolute() and candidate.is_file() and _use_unrar(candidate):
            return

    if sys.platform == "win32":
        target = "windows-x86_64"
    elif sys.platform == "linux" and platform.machine().lower() in {"x86_64", "amd64"}:
        target = "linux-x86_64"
    else:
        return

    bundled = Path(__file__).resolve().parent / "vendor" / "unrar" / target / executable
    if bundled.is_file():
        _use_unrar(bundled)
    # rarfile can still find its other supported tools if neither UnRAR works.
