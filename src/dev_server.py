#!/usr/bin/env python3
"""
Compatibility entrypoint for src/dev_server.py -> delegates to scripts/dev_server.py.
"""

import os
import runpy
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_PATH = os.path.join(_REPO_ROOT, "scripts", "dev_server.py")

if __name__ == "__main__":
    runpy.run_path(_SCRIPT_PATH, run_name="__main__")
