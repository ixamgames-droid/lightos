"""DOC-11 Galerie-Render-Server (Dev-/Doku-Werkzeug).

Liefert den visualizer-Ordner statisch aus (GET, fuer gallery_render.html + Module +
Assets) UND nimmt per POST /save/<name> ein data:image/png;base64,... entgegen und
schreibt es nach docs/img/fixture_gallery/<name>.png. So wandert das gerenderte
Canvas-PNG direkt aus dem Browser auf die Platte, ohne durch den Agenten-Kontext zu
laufen. Nur lokal (127.0.0.1).

Start (aus dem Repo-Root):
  python tools/gallery_server.py 8778
Dann im Preview-Pane: http://127.0.0.1:8778/gallery_render.html?type=<viz_model>
"""
import base64
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIS_DIR = os.path.join(REPO, "src", "ui", "visualizer")
OUT_DIR = os.path.join(REPO, "docs", "img", "fixture_gallery")
os.makedirs(OUT_DIR, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=VIS_DIR, **kw)

    def do_POST(self):
        if not self.path.startswith("/save/"):
            self.send_error(404)
            return
        name = os.path.basename(self.path[len("/save/"):]) or "unnamed"
        if not name.endswith(".png"):
            name += ".png"
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", "replace")
        if "," in body:
            body = body.split(",", 1)[1]      # data:image/png;base64,<...>
        try:
            data = base64.b64decode(body)
        except Exception as e:
            self.send_error(400, f"bad base64: {e}")
            return
        with open(os.path.join(OUT_DIR, name), "wb") as f:
            f.write(data)
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(f"saved {name} ({len(data)} bytes)".encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8778
    print(f"serving {VIS_DIR} on 127.0.0.1:{port}, saving PNGs to {OUT_DIR}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
