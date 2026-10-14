"""DOC-71 — alle Anleitungen sagen dasselbe darueber, was ein Blackout mit einem Laser macht.

**Der Befund (Bedientest QA-96, 11.10.2026):** die Anleitungen widersprachen
sich. „Erste Schritte“ und die Laser-Anleitung sagen seit LAS-25: ein Laser
bekommt beim Blackout den Aus-Wert aus seinem Geraeteprofil, und der ist nicht
immer 0. „Ausgabe einrichten“, die Anleitung zur VC-Taste und die Skript-
Referenz sagten weiter „Laser und Nebel gehen ganz aus“ bzw. „Laser/Nebel auf
0“ — die englischen Fassungen ebenso, und (von der Suche unten gefunden) das
Handbuch ``docs/ANLEITUNG.md``.

**Was stimmt (am Code geprueft, ``OutputManager._send_all``):** der Blackout
nullt alle Kanaele eines Lasers und schreibt DANACH die Aus-Werte, die das
Profil kennt. Ein Laser ohne Aus-Wert im Profil bekommt also ueberall 0 — und
strahlt weiter, wenn 0 an seiner Betriebsart nicht „aus“ heisst.

Zwei Teile: die Anleitungen (kein Absatz verspricht mehr „ganz aus“ fuer Laser,
ohne den Aus-Wert zu nennen) und das Verhalten selbst am echten Sende-Pfad, mit
dem Aufbau aus ``test_las25_blackout_laser_aus``.
"""
import os
import re
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager
from test_las25_blackout_laser_aus import _Ch, _FM, _Fx, _Rg

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(_REPO, "docs")

# Arbeits- und Verlaufsdokumente beschreiben, was einmal war — nicht geprueft.
_KEIN_HANDBUCH = re.compile(
    r"AUDIT|_PLAN|PLAN_|DESIGN|NOTES|OPEN_POINTS|BACKLOG|CHANGELOG|MASTERPLAN|"
    r"ROADMAP|UEBERSICHT|REVIEW|HISTORY", re.IGNORECASE)

# „… ganz aus / komplett aus / auf 0 / completely off“ — das alte Versprechen.
_GANZ_AUS = re.compile(
    r"ganz aus|komplett aus|gehen aus|auf 0\b|completely off|go(?:es)? (?:completely )?off|"
    r"to 0\b", re.IGNORECASE)
_AUS_WERT = re.compile(r"Aus-Wert|off value", re.IGNORECASE)

# Die Stellen, an denen der Widerspruch stand (Datei, Anfang des Absatzes).
_STELLEN = (
    ("ANLEITUNG.md", "- **BLACKOUT**"),
    ("anleitung_ausgabe_einrichten/ANLEITUNG.md", "Geräte ohne Dimmerkanal und Nebelmaschinen"),
    ("anleitung_ausgabe_einrichten/ANLEITUNG.en.md", "Fixtures without a dimmer channel and fog"),
    ("anleitung_erste_schritte/ANLEITUNG.md", "6. **BLACKOUT**"),
    ("anleitung_erste_schritte/ANLEITUNG.en.md", "6. **BLACKOUT**"),
    ("anleitung_vc_widgets/01_button.md", "| Blackout |"),
    ("anleitung_vc_widgets/01_button.md", "Bei der Aktion **Blackout**"),
    ("anleitung_vc_widgets/01_button.en.md", "| Blackout |"),
    ("anleitung_vc_widgets/01_button.en.md", "With the action **Blackout**"),
    ("components/engine/script.md", "| `blackout on"),
    ("anleitung_laser/ANLEITUNG_LASER.md", "- **BLACKOUT** (global)"),
)


def _lies(rel: str) -> str:
    with open(os.path.join(DOCS, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


_LISTENPUNKT = re.compile(r"\s*(?:[-*]|\d+\.)\s+\S")


def _absaetze(text: str):
    """(Zeilennummer, Absatz). Tabellenzeilen und Listenpunkte zaehlen einzeln
    — jeder ist eine eigene Aussage."""
    zeile, block, start = 0, [], 1
    for roh in text.split("\n"):
        zeile += 1
        tabelle = roh.lstrip().startswith("|")
        if block and (tabelle or not roh.strip() or _LISTENPUNKT.match(roh)):
            yield start, "\n".join(block)
            block = []
        if tabelle:
            yield zeile, roh
        elif roh.strip():
            if not block:
                start = zeile
            block.append(roh)
    if block:
        yield start, "\n".join(block)


def _handbuecher():
    for ordner, _unter, dateien in os.walk(DOCS):
        for name in sorted(dateien):
            if name.endswith(".md") and not _KEIN_HANDBUCH.search(name):
                yield os.path.relpath(os.path.join(ordner, name), DOCS).replace(os.sep, "/")


class AnleitungenTests(unittest.TestCase):
    def test_kein_absatz_verspricht_ganz_aus_ohne_den_aus_wert(self):
        """★ Ueber ALLE Anleitungen: wer in einem Absatz Laser, Blackout und
        „ganz aus / auf 0“ nennt, nennt dort auch den Aus-Wert."""
        funde = []
        for rel in _handbuecher():
            for nr, absatz in _absaetze(_lies(rel)):
                if ("laser" in absatz.lower() and "blackout" in absatz.lower()
                        and _GANZ_AUS.search(absatz) and not _AUS_WERT.search(absatz)):
                    funde.append(f"docs/{rel}:{nr}: {absatz.strip()[:110]}")
        self.assertEqual(funde, [], "\n" + "\n".join(funde))

    def test_die_elf_stellen_nennen_den_aus_wert(self):
        for rel, anfang in _STELLEN:
            with self.subTest(datei=rel, stelle=anfang):
                treffer = [a for _nr, a in _absaetze(_lies(rel))
                           if a.lstrip().startswith(anfang)]
                self.assertEqual(len(treffer), 1, f"Absatz „{anfang}…“ nicht (eindeutig) gefunden")
                self.assertRegex(treffer[0], _AUS_WERT)

    def test_niemand_sagt_mehr_laser_und_nebel_in_einem_atemzug(self):
        """Die drei alten Saetze, woertlich."""
        alt = ("Laser und Nebel gehen", "Laser/Nebel ganz aus", "Dimmer/Farbe/Laser/Nebel auf 0",
               "lasers and fog machines go completely off", "lasers/fog completely off",
               "lasers and fog go completely off")
        for rel in _handbuecher():
            text = _lies(rel)
            for satz in alt:
                with self.subTest(datei=rel, satz=satz):
                    self.assertNotIn(satz, text)

    def test_wo_der_laser_weiterstrahlen_kann_steht_der_not_aus(self):
        """Wer den Vorbehalt nennt, nennt auch den Ausweg."""
        for rel in _handbuecher():
            for nr, absatz in _absaetze(_lies(rel)):
                if re.search(r"weiterstrahl|strahlt \w+ weiter|keep emitting", absatz):
                    with self.subTest(stelle=f"docs/{rel}:{nr}"):
                        nah = _lies(rel)
                        i = nah.index(absatz)
                        self.assertRegex(nah[max(0, i - 1500): i + len(absatz) + 1500],
                                         r"NOT-AUS|emergency stop")


# ── das Verhalten, das die Anleitungen beschreiben ──────────────────────────
# Laser A (fid 7, ab Adresse 10): Betriebsart 0-49 „Auto“, 50-99 „Laser off“ —
# Aus-Wert 50. Laser B (fid 8, ab 30): Programmwahl ohne Aus-Bereich, das Profil
# kennt KEINEN Aus-Wert. Dazu ein Nebelgeraet (fid 9, ab 50).
_A, _B, _NEBEL = _Fx(7, 1, 10, "laser"), _Fx(8, 1, 30, "laser"), _Fx(9, 1, 50, "smoke")
_KANAELE = {
    7: [_Ch("shutter", 1, [_Rg(0, 49, "Auto run", "open"),
                           _Rg(50, 99, "Laser off", "closed"),
                           _Rg(100, 255, "Manual", "open")]),
        _Ch("laser_bank", 2), _Ch("laser_x", 3)],
    8: [_Ch("macro", 1, [_Rg(0, 127, "Auto"), _Rg(128, 255, "Sound")]),
        _Ch("laser_bank", 2), _Ch("laser_x", 3)],
    9: [_Ch("fog", 1), _Ch("fan", 2)],
}


def _aufbau():
    om = OutputManager()
    om.add_universe(1)
    st = AppState.__new__(AppState)
    st.universes = om.universes
    st.programmer = {7: {"shutter": 120, "laser_bank": 5, "laser_x": 90},
                     8: {"macro": 200, "laser_bank": 7, "laser_x": 60},
                     9: {"fog": 255, "fan": 128}}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_A, _B, _NEBEL]
    st._prog_lock = threading.RLock()
    st.output_manager = om
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._emit = lambda *a, **k: None
    st._rebuild_render_plan()
    return st, om


class VerhaltenTests(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _KANAELE[fx.fid]
        self.addCleanup(setattr, A, "get_channels_for_patched", self._orig)
        self.st, self.om = _aufbau()

    def _bild(self):
        self.st._render_frame(0.025)
        self.om._send_all()
        return self.om._display_frame[1]

    def _kanaele(self, bild, fx, n):
        return [bild[fx.address - 1 + i] for i in range(n)]

    def test_vorbedingung_alles_laeuft(self):
        bild = self._bild()
        self.assertEqual(self._kanaele(bild, _A, 3), [120, 5, 90])
        self.assertEqual(self._kanaele(bild, _B, 3), [200, 7, 60])
        self.assertEqual(self._kanaele(bild, _NEBEL, 2), [255, 128])

    def test_blackout_laser_mit_aus_wert(self):
        """„Laser bekommen den Aus-Wert aus ihrem Profil, die uebrigen
        Laser-Kanaele gehen auf 0“ — und der Aus-Wert ist hier nicht 0."""
        self.om.set_blackout(True)
        self.assertEqual(self._kanaele(self._bild(), _A, 3), [50, 0, 0])

    def test_blackout_laser_ohne_aus_wert_bekommt_ueberall_null(self):
        """„Kennt das Profil keinen Aus-Wert, bleibt es bei der 0 auf allen
        Kanaelen“ — bei diesem Laser hiesse 0 „Auto“: er liefe weiter."""
        self.assertNotIn(_B.address, self.om._gm_laser_aus_mask.get(1, {}))
        self.om.set_blackout(True)
        self.assertEqual(self._kanaele(self._bild(), _B, 3), [0, 0, 0])

    def test_blackout_nebel_geht_ganz_auf_null(self):
        self.om.set_blackout(True)
        self.assertEqual(self._kanaele(self._bild(), _NEBEL, 2), [0, 0])

    def test_ziel_blackout_gilt_dieselbe_regel_und_nur_im_ziel(self):
        self.st.set_target_blackout("taste", fids=[7, 8])
        bild = self._bild()
        self.assertEqual(self._kanaele(bild, _A, 3), [50, 0, 0])
        self.assertEqual(self._kanaele(bild, _B, 3), [0, 0, 0])
        self.assertEqual(self._kanaele(bild, _NEBEL, 2), [255, 128], "nicht im Ziel")


if __name__ == "__main__":
    unittest.main()
