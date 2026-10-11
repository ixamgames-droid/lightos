"""VIZ-85 / Codex-Review #966: die Bildwiederholrate folgt einem Bildschirmwechsel.

Bis hierhin kam die Hz nur einmal per URL (``&hz=``) an die Seite. Das Popout
wird aber erst NACH dem Laden per ``_place_on_free_screen()`` auf den
Zweitschirm geschoben — ein 30-Hz-Fernseher wurde dann mit der Hz des
Hauptschirms bewertet und die dynamische Aufloesung griff im Hauptszenario
nicht. Jetzt reicht ``_on_screen_changed`` die Hz des neuen Bildschirms per
``runJavaScript`` an ``window.__lightos.setDisplayHz`` weiter.
"""
import os
import pathlib
import subprocess
import tempfile
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.visualizer import visualizer_window as VW

_app = QApplication.instance() or QApplication([])

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "ui" / "visualizer" / "scene_src"


class _Seite:
    def __init__(self):
        self.js = []

    def runJavaScript(self, code, *a):
        self.js.append(code)


class _Ansicht:
    def __init__(self):
        self._seite = _Seite()

    def page(self):
        return self._seite


class _Schirm:
    def __init__(self, hz, ratio=1.0):
        self._hz, self._ratio = hz, ratio

    def refreshRate(self):
        return self._hz

    def devicePixelRatio(self):
        return self._ratio


def _fenster():
    ratios = []
    ns = types.SimpleNamespace(
        _view=_Ansicht(),
        _bridge=types.SimpleNamespace(push_pixel_ratio=ratios.append),
    )
    return ns, ratios


def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


class BildschirmwechselTest(unittest.TestCase):
    def test_wechsel_auf_30hz_tv_schickt_neue_hz(self):
        fenster, ratios = _fenster()
        VW.VisualizerWindow._on_screen_changed(fenster, _Schirm(29.97, 2.5))
        self.assertEqual(ratios, [2.5])
        js = fenster._view.page().js
        self.assertEqual(len(js), 1, js)
        self.assertIn("setDisplayHz", js[0])
        self.assertIn("29.97", js[0])

    def test_unplausible_hz_loescht_die_angabe(self):
        for hz in (0.0, 5.0, 1000.0):
            fenster, _ = _fenster()
            VW.VisualizerWindow._on_screen_changed(fenster, _Schirm(hz))
            (js,) = fenster._view.page().js
            self.assertTrue(js.rstrip().endswith("(0);"), (hz, js))

    def test_kaputte_seite_bricht_nichts(self):
        class _Kaputt:
            def page(self):
                raise RuntimeError("weg")
        self.assertEqual(VW.push_bildschirm_hz(_Kaputt(), _Schirm(60.0)), 60.0)

    def test_js_seite_kennt_setdisplayhz(self):
        app_js = (_SRC / "app.js").read_text(encoding="utf-8")
        self.assertIn("setDisplayHz: (hz) => dynamicResolution.setDisplayHz(hz)", app_js)
        renderer_js = (_SRC / "scene" / "renderer.js").read_text(encoding="utf-8")
        self.assertIn("window.__lightosDisplayHz", renderer_js)

    @unittest.skipUnless(_node_verfuegbar(), "node fehlt")
    def test_schnipsel_ruft_api_oder_parkt(self):
        code = VW._hz_js(29.97)
        treiber = (
            "const out = [];\n"
            "globalThis.window = { __lightos: { setDisplayHz: h => out.push(h) } };\n"
            f"{code}\n"
            "globalThis.window = {};\n"
            f"{code}\n"
            "out.push(window.__lightosDisplayHz);\n"
            "console.log(JSON.stringify(out));\n"
        )
        with tempfile.TemporaryDirectory() as verz:
            pfad = os.path.join(verz, "t.js")
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(treiber)
            p = subprocess.run(["node", pfad], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "[29.97,29.97]")


if __name__ == "__main__":
    unittest.main()
