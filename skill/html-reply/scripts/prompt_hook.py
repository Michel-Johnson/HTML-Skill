#!/usr/bin/env python3
"""No-op compatibility shim for tasks that cached an old HTML prompt hook."""

from __future__ import annotations

import sys


def main() -> int:
    sys.stdin.read()
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
