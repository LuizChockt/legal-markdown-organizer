"""Run from a checkout with: python main.py PATH [--dry-run]."""

import sys

# Keep checkout previews free of Python-generated __pycache__ directories.
sys.dont_write_bytecode = True

from legal_organizer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
