"""OUT-ENTTECUNIV — der Ausgabe-Tab verband immer Universum 1.

★ LIVE GEFUNDEN AN DAVIDS GERAET (2026-08-05). Sein LED-Balken haengt auf
Universum 3 am Enttec. Die Show lief, der 2D/3D-Viewer zeigte alles korrekt —
und der Balken blieb dunkel. Gemessen:

    Enttec-Adapter:  {1: '/dev/ttyUSB0'}       <- Adapter auf Universum 1
    Puffer U3:       CH1=255, 145 Kanaele > 0  <- die Werte waren da
    Gesendet (U1):   0 Bytes > 0               <- ein LEERER Puffer ging raus

LightOS rechnete also richtig und sendete das falsche Universum.

URSACHE: `_spin_enttec_univ` wurde nie mit dem gespeicherten Wert vorbelegt.
Vier Fundstellen fuer das Widget — erzeugen, Range, ins Formular, auslesen.
Keine einzige LADENDE. Die Spinbox stand damit bei jedem Oeffnen des Tabs auf
dem Minimum ihrer Range (1). Ein Klick auf „Verbinden" nahm diese 1, oeffnete
den Enttec auf Universum 1 — und schrieb das ueber `_persist_output` zurueck in
universes.json.

Damit erklaert sich auch HW-5c, der seit Wochen offene „Rueckfall in
universes.json, Ursache offen": es war kein Rueckfall, sondern ein Ueberschreiben
durch die UI. Und Davids Beobachtung *„wenn ich im Ausgabe-Tab auf den Enttec
gehe und den Tab wieder oeffne, ist er nicht mehr angewaehlt"* war exakt dieses
Symptom.
"""
import io
import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _mit_konfig(zeilen):
    """Schreibt eine universes.json an den Ort, den das Modul liest."""
    from src.ui.widgets import output_config as oc
    d = tempfile.mkdtemp(prefix="lightos_univ_")
    p = os.path.join(d, "universes.json")
    io.open(p, "w", encoding="utf-8").write(
        json.dumps(zeilen, indent=2, ensure_ascii=False))
    alt = oc._UNIV_CONFIG_PATH
    oc._UNIV_CONFIG_PATH = p
    return oc, alt, d


class GespeichertesEnttecUniversumTest(unittest.TestCase):

    def _lauf(self, zeilen):
        import shutil
        oc, alt, d = _mit_konfig(zeilen)
        try:
            return oc._gespeichertes_enttec_universum()
        finally:
            oc._UNIV_CONFIG_PATH = alt
            shutil.rmtree(d, ignore_errors=True)

    def test_davids_fall_universum_3(self):
        self.assertEqual(self._lauf([
            {"num": 3, "name": "LED-Balken", "output": "Enttec",
             "patch": "/dev/ttyUSB0"}]), 3)

    def test_ohne_enttec_zeile_bleibt_es_bei_1(self):
        # Frische Installation — dort ist 1 richtig.
        self.assertEqual(self._lauf([
            {"num": 4, "output": "ArtNet", "patch": "2.0.0.1"}]), 1)

    def test_leere_konfiguration(self):
        self.assertEqual(self._lauf([]), 1)

    def test_mehrere_enttec_zeilen_kleinste_gewinnt(self):
        # Ein Enttec Pro hat EINEN Ausgang; mehrere Zeilen sind bereits ein
        # Konfigurationsfehler. Wichtig ist nur, dass die Wahl vorhersehbar ist.
        self.assertEqual(self._lauf([
            {"num": 7, "output": "Enttec", "patch": "/dev/ttyUSB0"},
            {"num": 3, "output": "Enttec", "patch": "/dev/ttyUSB0"}]), 3)

    def test_kaputte_eintraege_werfen_nicht(self):
        # Eine unlesbare Zeile darf den Tab nicht aufhalten.
        self.assertEqual(self._lauf([
            {"num": "abc", "output": "Enttec"},
            {"output": "Enttec"},
            {"num": 99, "output": "Enttec"},        # ausserhalb 1..32
            {"num": 5, "output": "Enttec", "patch": "/dev/ttyUSB0"}]), 5)

    def test_andere_ausgaenge_zaehlen_nicht(self):
        self.assertEqual(self._lauf([
            {"num": 2, "output": "sACN"},
            {"num": 6, "output": "Disabled"},
            {"num": 8, "output": "Enttec", "patch": "/dev/ttyUSB0"}]), 8)


class SpinboxWirdVorbelegtTest(unittest.TestCase):
    """★ Der Test, der den Fehler ueberhaupt gefunden haette.

    Er prueft nicht die Hilfsfunktion, sondern dass das WIDGET sie benutzt —
    genau die Luecke, an der es lag: die Funktion haette es auch vorher schon
    geben koennen, ohne dass jemand sie aufruft.
    """

    def test_spinbox_uebernimmt_den_gespeicherten_wert(self):
        import shutil
        from PySide6.QtWidgets import QApplication
        oc, alt, d = _mit_konfig([
            {"num": 3, "name": "LED-Balken", "output": "Enttec",
             "patch": "/dev/ttyUSB0"}])
        app = QApplication.instance() or QApplication([])
        try:
            dlg = oc.OutputConfigDialog()
            try:
                self.assertEqual(dlg._spin_enttec_univ.value(), 3,
                                 "Ausgabe-Tab verbindet sonst Universum 1 und "
                                 "ueberschreibt die gespeicherte Wahl")
            finally:
                dlg.deleteLater()
        finally:
            oc._UNIV_CONFIG_PATH = alt
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
