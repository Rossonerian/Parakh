"""Interactive terminal console (optional extra: ``pip install -e '.[tui]'``).

Importing this package imports Textual; the CLI turns an ImportError into an
install hint so the core lab stays dependency-free.
"""

from model_lab.tui.app import ParakhApp, run_tui

__all__ = ["ParakhApp", "run_tui"]
