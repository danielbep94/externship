#!/usr/bin/env python3
"""
Servidor HTTP local sin caché (Cache-Control: no-store) para la Arquitectura Modular CHUBB.
Enruta:
- /, /index.html, /css/*, /js/*, /assets/* -> app/
- /data.json -> data/curated/data.json (con fallback a root data.json)
- /data/mexico_estados.geojson -> data/raw/mexico_estados.geojson
Incluye protección explícita contra Path Traversal.
"""

import http.server
import os
import posixpath
import socketserver
import sys
import urllib.parse
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
DATA_CURATED = REPO_ROOT / "data" / "curated" / "data.json"
DATA_RAW_GEOJSON = REPO_ROOT / "data" / "raw" / "mexico_estados.geojson"


class ModularNoCacheHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP Request Handler serving app/ and curated/raw data with no-cache headers."""

    def translate_path(self, path: str) -> str:
        parsed_path = urllib.parse.urlsplit(path).path
        clean_path = posixpath.normpath(urllib.parse.unquote(parsed_path)).lstrip("/")

        if clean_path in ("", "index.html"):
            candidate = APP_DIR / "index.html"
            if candidate.exists():
                return str(candidate)
            return str(REPO_ROOT / "index.html")

        if clean_path == "data.json":
            if DATA_CURATED.exists():
                return str(DATA_CURATED)
            return str(REPO_ROOT / "data.json")

        if clean_path == "data/mexico_estados.geojson":
            if DATA_RAW_GEOJSON.exists():
                return str(DATA_RAW_GEOJSON)
            return str(REPO_ROOT / "data" / "mexico_estados.geojson")

        for prefix in ("css/", "js/", "assets/"):
            if clean_path.startswith(prefix):
                target = (APP_DIR / clean_path).resolve()
                if str(target).startswith(str(APP_DIR.resolve())) and target.exists():
                    return str(target)

        target_root = (REPO_ROOT / clean_path).resolve()
        if not str(target_root).startswith(str(REPO_ROOT.resolve())):
            return str(APP_DIR / "nonexistent_forbidden")
        return str(target_root)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with ReusableTCPServer(("", PORT), ModularNoCacheHTTPRequestHandler) as httpd:
        print(f"Serving Modular CHUBB App (No-Cache HTTP) on http://localhost:{PORT}/index.html", flush=True)
        httpd.serve_forever()

