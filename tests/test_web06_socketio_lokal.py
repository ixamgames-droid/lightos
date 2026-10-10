"""WEB-06: Die Web-Remote laedt nichts aus dem Internet.

Befund: ``src/web/templates/index.html`` holte ``socket.io.min.js`` von
``cdn.socket.io``. Am Veranstaltungsort haengt das Handy nur im LightOS-WLAN —
ohne Internet kam die Seite, aber ``io()`` fehlte: keine Verbindung, kein Fader,
kein Blackout. Dazu lief ein fremdes Skript ohne Integritaetspruefung.

Festgehalten wird:
* kein Template unter ``src/web/templates`` verweist auf eine fremde Adresse
  (Skript, Stylesheet, Schrift, Bild);
* der Socket.IO-Client liegt unter ``src/web/static/`` — Byte-gleich mit der
  offiziellen Datei (SHA-256), passend zum Protokoll des installierten Servers;
* Flask liefert ihn aus, auch OHNE Anmeldung (die Seite braucht ihn vor dem
  Handshake) — geprueft mit dem Test-Client, ohne Server-Port;
* die Datei steht im Windows-Bundle und in der Pflichtliste des Selbsttests.
"""
import hashlib
import importlib.util
import os
import pathlib
import re
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "web" / "templates"
REL_JS = "src/web/static/socket.io.min.js"
JS = ROOT / REL_JS

#: socket.io-client 4.7.5, ``dist/socket.io.min.js`` aus dem npm-Paket
#: (https://registry.npmjs.org/socket.io-client/-/socket.io-client-4.7.5.tgz);
#: dieselben Bytes liefert https://cdn.socket.io/4.7.5/socket.io.min.js.
SHA256 = "73eba16bc895fdfa454e27ecb80def31ede8d861f99e175ff93b110eabec044f"

#: Alles, was der Browser von woanders nachladen wuerde: ``src=``/``href=`` mit
#: Schema oder protokoll-relativ (``//host``), CSS ``url(...)`` und ``@import``.
_EXTERN = re.compile(
    r"""(?:\b(?:src|href|action|poster|data)\s*=\s*["']?\s*(?:https?:)?//"""
    r"""|url\(\s*["']?\s*(?:https?:)?//"""
    r"""|@import\s+["']?\s*(?:https?:)?//"""
    r"""|\bimport\s*(?:\(|[^;]*?from)\s*["'](?:https?:)?//)""",
    re.IGNORECASE)


def externe_verweise(html: str) -> list[str]:
    return [m.group(0) for m in _EXTERN.finditer(html)]


class SuchmusterTest(unittest.TestCase):
    """Gegenprobe: das Muster erkennt die Faelle, um die es geht."""

    def test_erkennt_fremde_quellen(self):
        for html in (
            '<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>',
            "<script src='http://example.org/a.js'></script>",
            '<script src="//cdn.example.org/a.js"></script>',
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=X">',
            "<style>@import 'https://example.org/a.css';</style>",
            "<style>@font-face{src:url(https://example.org/a.woff2)}</style>",
            '<img src=https://example.org/a.png>',
            '<script type="module">import x from "https://example.org/m.js";</script>',
        ):
            with self.subTest(html=html):
                self.assertTrue(externe_verweise(html))

    def test_laesst_lokale_quellen_durch(self):
        for html in (
            '<script src="/static/socket.io.min.js"></script>',
            "<script src=\"{{ url_for('static', filename='socket.io.min.js') }}\"></script>",
            "<style>body{background:url(/static/a.png)}</style>",
            "fetch('/api/status')  // Kommentar",
        ):
            with self.subTest(html=html):
                self.assertEqual(externe_verweise(html), [])


class TemplateOhneFremdquellenTest(unittest.TestCase):
    def test_es_gibt_templates(self):
        # Gegenprobe: ein verschobener Ordner liesse den Waechter leer gruen werden.
        self.assertTrue((TEMPLATES / "index.html").is_file())

    def test_kein_template_laedt_von_fremder_adresse(self):
        for p in sorted(TEMPLATES.rglob("*")):
            if not p.is_file():
                continue
            with self.subTest(template=p.name):
                self.assertEqual(externe_verweise(p.read_text(encoding="utf-8")), [])

    def test_index_bindet_die_lokale_datei_ein(self):
        html = (TEMPLATES / "index.html").read_text(encoding="utf-8")
        self.assertIn("socket.io.min.js", html)
        self.assertNotIn("cdn.socket.io", html)


class LokaleDateiTest(unittest.TestCase):
    def test_datei_ist_die_offizielle(self):
        self.assertTrue(JS.is_file(), f"{REL_JS} fehlt")
        self.assertEqual(hashlib.sha256(JS.read_bytes()).hexdigest(), SHA256)

    def test_version_passt_zum_server(self):
        # python-socketio 5.x / python-engineio 4.x sprechen Socket.IO-Protokoll 5
        # (Engine.IO 4) — das ist der JS-Client 3.x/4.x. Ein Sprung des Servers auf
        # eine neue Hauptversion muss hier auffallen, bevor die Seite stumm bleibt.
        from importlib import metadata
        try:
            sio = metadata.version("python-socketio")
            eio = metadata.version("python-engineio")
        except metadata.PackageNotFoundError:
            self.skipTest("python-socketio nicht installiert")
        self.assertEqual(sio.split(".")[0], "5", sio)
        self.assertEqual(eio.split(".")[0], "4", eio)
        kopf = JS.read_bytes()[:200].decode("ascii", "replace")
        self.assertIn("Socket.IO v4.", kopf)

    def test_lizenzhinweis(self):
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn(REL_JS, notices)
        self.assertIn("licenses/MIT-socket.io.txt", notices)
        self.assertIn(SHA256, notices)
        mit = (ROOT / "licenses" / "MIT-socket.io.txt").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", mit)
        self.assertIn("Guillermo Rauch", mit)


class BundleTest(unittest.TestCase):
    def test_datei_liegt_im_windows_bundle(self):
        spec = importlib.util.spec_from_file_location(
            "bundle_inhalt_web06",
            ROOT / "packaging" / "windows" / "bundle_inhalt.py")
        bi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bi)
        self.assertIn(REL_JS, bi.dateien(str(ROOT)))
        ziele = {(os.path.basename(q), z.replace(os.sep, "/"))
                 for q, z in bi.datas(str(ROOT))}
        # gleicher relativer Pfad wie im Repo -> Flask findet ``static`` neben app.py
        self.assertIn(("socket.io.min.js", "src/web/static"), ziele)

    def test_selbsttest_verlangt_die_datei(self):
        from src.core import selbsttest
        self.assertIn(REL_JS, selbsttest.PFLICHT_RESSOURCEN)
        self.assertEqual(
            [f for f in selbsttest.pruefe_ressourcen(str(ROOT)) if "web" in f], [])


@unittest.skipUnless(HAS_FLASK, "Flask / flask-socketio nicht installiert")
class AuslieferungTest(unittest.TestCase):
    """Nur Flask-Test-Client — es wird kein Port geoeffnet."""

    def setUp(self):
        import src.web.app as webapp
        self._patch = mock.patch.object(webapp, "get_state", create=True)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.app, _sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()     # frisch: NICHT angemeldet

    def test_static_ordner_liegt_neben_app(self):
        self.assertEqual(os.path.realpath(self.app.static_folder),
                         os.path.realpath(ROOT / "src" / "web" / "static"))

    def test_route_liefert_die_datei_ohne_anmeldung(self):
        r = self.client.get("/static/socket.io.min.js")
        try:
            self.assertEqual(r.status_code, 200)
            self.assertIn("javascript", r.mimetype)
            self.assertEqual(hashlib.sha256(r.data).hexdigest(), SHA256)
        finally:
            r.close()

    def test_geschuetzte_route_bleibt_ohne_anmeldung_zu(self):
        # Gegenprobe: der 200 oben kommt nicht daher, dass das Gate offen stuende.
        self.assertEqual(self.client.get("/api/status").status_code, 403)

    def test_startseite_verweist_auf_die_lokale_route(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertEqual(externe_verweise(html), [])
        quellen = re.findall(r'<script[^>]*\bsrc="([^"]+)"', html)
        self.assertEqual(quellen, ["/static/socket.io.min.js"])
        for q in quellen:
            r2 = self.client.get(q)
            try:
                self.assertEqual(r2.status_code, 200, q)
            finally:
                r2.close()


if __name__ == "__main__":
    unittest.main()
