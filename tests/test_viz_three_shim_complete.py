"""VIZ-SHIM: jeder benutzte `THREE.<Name>` muss im Wrapper-Modul deklariert sein.

`src/ui/visualizer/scene_src/three/three.js` macht das globale `window.THREE`
fuer die ES-Module importierbar — ueber eine **handgepflegte Namensliste**. Die
Liste wurde einmal aus `stage_scene.html` erhoben; die Module unter `scene_src/`
hat nie jemand dagegen geprueft.

**Warum das gefaehrlich ist:** ein fehlender Name wirft nicht. Der Zugriff ueber
den Modul-Namespace liefert `undefined`, und `undefined` sieht in three wie ein
gueltiger Wert aus. Beide Fundstellen vom 2026-08-03 waren still:

* `PCFShadowMap` -> `renderer.shadowMap.type = undefined` auf Low-Spec, Rueckfall
  auf `SHADOWMAP_TYPE_BASIC`: harte Schatten statt der beschriebenen PCF-Filterung.
* `BackSide` -> die Raum-Huelle bekam `side: undefined`, three faellt auf
  `FrontSide` zurueck. Mit einem Strahl aus der Raummitte gemessen: 2 Treffer mit
  `BackSide`, **0** ohne — die Huelle war von innen unsichtbar, das ganze Feature
  wirkungslos seit dem Bau.

**Warum dieser Test statisch ist und nicht in der Seite laeuft:** ein Lauftest
kann nur pruefen, was DEKLARIERT ist (`Object.entries` sieht fehlende Namen
nicht). Genau der Fehler hier ist aber „Name gar nicht deklariert". Die Frage
ist also eine des Quelltextes — Zugriffsmenge gegen Exportmenge — und die ist
ohne Qt, ohne WebGL und in Millisekunden beantwortbar.
"""
from __future__ import annotations

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCENE_SRC = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src")
_SHIM = os.path.join(_SCENE_SRC, "three", "three.js")

# `THREE.Foo` — der Namespace-Import heisst in allen Modulen so.
_ZUGRIFF = re.compile(r"\bTHREE\.([A-Za-z_][A-Za-z0-9_]*)")
# Der Import, an dem man erkennt, dass eine Datei ueber den Shim geht.
_SHIM_IMPORT = re.compile(r"""from\s+['"][^'"]*three/three\.js['"]""")


def _js_dateien():
    for wurzel, _dirs, dateien in os.walk(_SCENE_SRC):
        for name in dateien:
            if name.endswith(".js"):
                yield os.path.join(wurzel, name)


def _shim_nutzer():
    """Dateien, die ihr `THREE` aus dem Wrapper-Modul beziehen.

    Nur fuer die gilt die Liste: klassische Scripts (three_local.js selbst,
    assets/OBJLoader.js) sehen das vollstaendige globale `window.THREE`.
    """
    for pfad in _js_dateien():
        if os.path.abspath(pfad) == os.path.abspath(_SHIM):
            continue
        text = open(pfad, encoding="utf-8", errors="replace").read()
        if _SHIM_IMPORT.search(text):
            yield pfad, text


def _exportierte_namen() -> set[str]:
    text = open(_SHIM, encoding="utf-8").read()
    block = text.split("export const {", 1)
    assert len(block) == 2, "Wrapper-Modul hat keinen `export const {`-Block mehr"
    inhalt = block[1].split("} = window.THREE;", 1)[0]
    namen = set()
    for zeile in inhalt.splitlines():
        zeile = zeile.split("//", 1)[0].strip().rstrip(",").strip()
        if zeile and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", zeile):
            namen.add(zeile)
    return namen


class ThreeShimVollstaendigTest(unittest.TestCase):

    def test_jeder_benutzte_name_ist_exportiert(self):
        exportiert = _exportierte_namen()
        self.assertGreater(len(exportiert), 30, "Export-Liste unerwartet klein")

        fehlend: dict[str, list[str]] = {}
        for pfad, text in _shim_nutzer():
            rel = os.path.relpath(pfad, _REPO)
            for zeilennr, zeile in enumerate(text.splitlines(), 1):
                if zeile.lstrip().startswith("//"):
                    continue
                for name in _ZUGRIFF.findall(zeile):
                    if name not in exportiert:
                        fehlend.setdefault(name, []).append(f"{rel}:{zeilennr}")

        self.assertFalse(fehlend, (
            "Diese THREE-Namen werden ueber den Modul-Namespace benutzt, stehen "
            "aber NICHT in der Export-Liste von scene_src/three/three.js — der "
            "Zugriff liefert dort still `undefined` (three meldet keinen Fehler, "
            "sondern faellt auf einen Default zurueck):\n  "
            + "\n  ".join(f"{n}: {', '.join(o[:3])}" for n, o in sorted(fehlend.items()))))

    def test_die_beiden_gefundenen_luecken_bleiben_geschlossen(self):
        """Nagelt die zwei Namen fest, die am 2026-08-03 gefehlt haben.

        Der allgemeine Test oben wuerde sie mitfangen — diese Zusicherung sagt
        aber, WAS kaputt war, und ueberlebt auch ein Umschreiben des Scanners.
        """
        exportiert = _exportierte_namen()
        for name, folge in (
            ("PCFShadowMap", "Low-Spec-Schatten fielen auf SHADOWMAP_TYPE_BASIC"),
            ("BackSide", "die Raum-Huelle war von innen unsichtbar"),
        ):
            self.assertIn(name, exportiert, f"{name} fehlt wieder — {folge}")

    def test_scanner_findet_die_shim_nutzer(self):
        """Gegenprobe: ein Scanner, der nichts findet, ist immer gruen.

        Ohne diese Zusicherung wuerde eine kaputte Pfad-/Regex-Aenderung den
        Test in eine Attrappe verwandeln, ohne dass es auffaellt.
        """
        nutzer = list(_shim_nutzer())
        self.assertGreater(len(nutzer), 15,
                           f"nur {len(nutzer)} Shim-Nutzer gefunden — Scanner kaputt?")
        namen = {n for _p, t in nutzer for n in _ZUGRIFF.findall(t)}
        self.assertGreater(len(namen), 30,
                           f"nur {len(namen)} THREE-Zugriffe gefunden — Regex kaputt?")


if __name__ == "__main__":
    unittest.main()
