#!/usr/bin/env python3
"""
Servidor HTTP local sin caché (Cache-Control: no-store)
Garantiza que Safari/Chrome carguen siempre la versión más reciente de index.html,
js/actuarial_engine.js, js/app.js y data.json sin retener versiones anteriores en caché.
"""

import http.server
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class NoCacheHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with ReusableTCPServer(("", PORT), NoCacheHTTPRequestHandler) as httpd:
        print(f"Serving No-Cache HTTP on http://localhost:{PORT}/index.html", flush=True)
        httpd.serve_forever()

