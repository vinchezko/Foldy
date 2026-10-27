"""Script entry point (what PyInstaller bundles; also `python src/run_foldy.py` during development)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # development: make the `foldy` package importable

from foldy.app import main  # noqa: E402

if __name__ == "__main__":
    main()
