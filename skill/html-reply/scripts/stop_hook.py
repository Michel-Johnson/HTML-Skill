#!/usr/bin/env python3
"""Allow legacy HTML Reply Stop Hook snapshots to finish without blocking.

Current installations do not register this hook.  The file remains because
long-running Codex tasks may keep an older Hook command snapshot and continue
invoking the same installed path.
"""

from __future__ import annotations

import sys


def main() -> int:
    sys.stdin.read()
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
