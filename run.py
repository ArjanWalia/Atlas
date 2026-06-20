#!/usr/bin/env python3
"""Convenience launcher so you can `python run.py` from anywhere.

Equivalent to `python -m atlas`, but works regardless of the current directory:
it puts this file's folder (the repo root, which contains the `atlas/` package) at
the front of sys.path before importing — so you never hit "No module named atlas".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from atlas.__main__ import main  # noqa: E402  (import after sys.path tweak)

if __name__ == "__main__":
    raise SystemExit(main())
