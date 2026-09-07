"""Application entry point."""

from __future__ import annotations

import tkinter as tk

from .ui import TahoeTelemetryApp


def main() -> None:
    root = tk.Tk()
    TahoeTelemetryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

