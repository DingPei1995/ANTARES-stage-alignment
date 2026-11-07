"""Start a program of the repository from its launcher (``QuickAlignment/QuickAlignment.py``, ...).

The launchers live in the tool folders (QuickAlignment/, RealSampleCalibration/, GoldFrameCalibration/);
they put ``src/`` on the import path and call `launch`. A missing package (PyQt5, numpy, matplotlib) is
reported in a dialog, since a double-clicked .pyw has no console.
"""

from __future__ import annotations

import importlib
import sys
import traceback


def show_error(title: str, text: str) -> None:
    """Without Qt there is no window to report in: try Tk, then the console."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, text)
    except Exception:
        print(text, file=sys.stderr)
        try:
            input("Press Enter to close...")
        except EOFError:
            pass


def launch(module: str, title: str = "QuickAlignment", argv: list[str] | None = None) -> int:
    """Import `module` and run its main(), reporting missing packages in a dialog."""
    try:
        main = importlib.import_module(module).main
    except ImportError:
        show_error(
            title,
            f"Could not start {title}, a package is missing:\n\n"
            + traceback.format_exc(limit=1)
            + "\nInstall the requirements with:\n    pip install -r requirements.txt",
        )
        return 1
    return main() if argv is None else main(argv)


__all__ = ["launch", "show_error"]
