#!/usr/bin/env python3
"""Convenience launcher so you can `python run.py` (same as `python -m atlas`)."""

from atlas.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
