"""NET-13: die Spalte „Ext-Universe" des Universe-Managers braucht einen
Bereichs-Guard — und zwar einen, der dem Ausgabetyp DERSELBEN ZEILE folgt.

**Gemessen vor dem Fix** (echter Dialog, echtes ``_univ_save``, 13 Zeilen):
sieben ungueltige bzw. sinnlose Eingaben landeten unveraendert in
``universes.json`` — Art-Net 40000/70000/-5, sACN 70000/0 — und der Dialog
meldete dazu genau EINE Sache: ``('info', 'Gespeichert')``. Kein Wort zur
Nummer.

**Was daraus im Sendepfad wird** (an den echten Paketbauern gemessen, s.
``test_grenzen_sind_am_sendepfad_gemessen``): Art-Net 40000 steht im 16-Bit-Feld,
der Empfaenger liest die unteren 15 Bit = Port-Address **7232**; sACN 70000
sendet auf ``70000 & 0xFFFF`` = **4464**; Art-Net 70000/-5 sprengen das Feld
(``struct.error`` bei JEDEM Frame, im Sende-Thread gefangen).

⚠️ **Die Grenze aus dem Backlog-Text („ausserhalb 1..63999 abweisen") ist
falsch** und wird hier ausdruecklich gegengeprueft: das ist nur die sACN-Grenze.
``out_universe`` gilt fuer Art-Net UND sACN, und Art-Net hat 15 Bit (0..32767).
Ein pauschales 1..63999 liesse fuer eine Art-Net-Zeile 40000 durch — genau den
Wert, der real bei 7232 ankommt.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QTableWidgetItem

import src.ui.widgets.output_config as oc

_app = QApplication.instance() or QApplication([])

# XPLAT-15: uebrig gebliebene Top-Level-Widgets nach jedem Test wirklich abbauen
# (Muster + Begruendung: tests/_qt_lifecycle.py).
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# ── Teil 1: die reine Frage „welcher Bereich gilt hier?" ─────────────────────

class TestBereichProAusgabetyp(unittest.TestCase):
    def test_artnet_ist_15_bit_und_null_basiert(self):
        self.assertEqual(oc._ext_universe_bereich("ArtNet"), (0, 32767))

    def test_sacn_ist_der_e131_bereich(self):
        self.assertEqual(oc._ext_universe_bereich("sACN"), (1, 63999))

    def test_typen_ohne_externes_universum_liefern_none(self):
        """Enttec sendet ohne Universum, Disabled sendet gar nicht — dort gibt es
        keinen Bereich, an dem man messen koennte. ``None`` heisst genau das und
        NICHT „Bereich unbekannt"."""
        for typ in ("Enttec", "Disabled", "", None, "   ", "Quatsch"):
            self.assertIsNone(oc._ext_universe_bereich(typ), typ)

    def test_leerzeichen_werden_toleriert(self):
        self.assertEqual(oc._ext_universe_bereich("  sACN "), (1, 63999))


class TestKlemmenProTyp(unittest.TestCase):
    def test_gueltige_werte_gehen_unveraendert_durch(self):
        """★ Gegenprobe: ein Guard, der auch gueltige Werte anfasst, ist kein
        Guard, sondern ein zweiter Fehler."""
        for typ, werte in (("ArtNet", (0, 1, 2, 512, 32766, 32767)),
                           ("sACN", (1, 2, 512, 63998, 63999))):
            for n in werte:
                self.assertEqual(oc._coerce_ext_universe(str(n), typ), (n, False),
                                 f"{typ} {n}")

    def test_artnet_ausserhalb_wird_geklemmt_und_gemeldet(self):
        self.assertEqual(oc._coerce_ext_universe("40000", "ArtNet"), (32767, True))
        self.assertEqual(oc._coerce_ext_universe("70000", "ArtNet"), (32767, True))
        self.assertEqual(oc._coerce_ext_universe("32768", "ArtNet"), (32767, True))
        self.assertEqual(oc._coerce_ext_universe("-5", "ArtNet"), (0, True))

    def test_sacn_ausserhalb_wird_geklemmt_und_gemeldet(self):
        self.assertEqual(oc._coerce_ext_universe("70000", "sACN"), (63999, True))
        self.assertEqual(oc._coerce_ext_universe("64000", "sACN"), (63999, True))
        self.assertEqual(oc._coerce_ext_universe("0", "sACN"), (1, True))
        self.assertEqual(oc._coerce_ext_universe("-5", "sACN"), (1, True))

    def test_der_typ_der_zeile_entscheidet(self):
        """★★ Der Kern des Items — und die Stelle, an der die im Backlog
        genannte pauschale Grenze 1..63999 versagt haette: DERSELBE Wert ist fuer
        sACN gueltig und fuer Art-Net zu gross."""
        self.assertEqual(oc._coerce_ext_universe("40000", "sACN"), (40000, False))
        self.assertEqual(oc._coerce_ext_universe("40000", "ArtNet"), (32767, True))
        # und andersherum an der Untergrenze: 0 ist Art-Net-gueltig, sACN nicht.
        self.assertEqual(oc._coerce_ext_universe("0", "ArtNet"), (0, False))
        self.assertEqual(oc._coerce_ext_universe("0", "sACN"), (1, True))

    def test_unparsebar_bleibt_still_und_ohne_wert(self):
        """Leer/Muell -> Feld weglassen = Default, ohne Meldung. Unveraendertes
        Verhalten; fuer ein leeres Feld zu warnen waere Laerm."""
        for text in ("", "   ", "abc", "1.5", None, "12a"):
            self.assertEqual(oc._coerce_ext_universe(text, "sACN"), (None, False),
                             repr(text))

    def test_enttec_und_disabled_behalten_ihren_wert(self):
        """★ Gegenprobe zur sicheren Richtung: eine getippte Nummer wird auf
        einer Zeile OHNE externes Universum weder geklemmt noch geloescht.
        Sie wirkt dort nicht (``add_enttec`` nimmt kein ``out_universe``, eine
        Disabled-Zeile bekommt gar keinen Adapter) — sie stillschweigend zu
        entfernen, waere teurer als sie stehen zu lassen."""
        for typ in ("Enttec", "Disabled"):
            self.assertEqual(oc._coerce_ext_universe("7", typ), (7, False), typ)
            self.assertEqual(oc._coerce_ext_universe("70000", typ), (70000, False), typ)

    def test_interner_universe_guard_bleibt_unberuehrt(self):
        """Gegenprobe A3D-33: die '#'-Spalte beantwortet eine ANDERE Frage
        (internes Universum, 1..32) und darf nicht mitgewandert sein."""
        self.assertEqual(oc._coerce_universe_num("70000", 1), (32, True))
        self.assertEqual(oc._coerce_universe_num("0", 1), (1, True))
        self.assertEqual((oc._UNIVERSE_MIN, oc._UNIVERSE_MAX), (1, 32))


# ── Teil 2: eine Frage, eine Stelle ─────────────────────────────────────────

class TestEineQuelleFuerGuardUndSpinboxen(unittest.TestCase):
    """Die Grenze der Tabellenspalte und die Range der Spinboxen daneben muessen
    DIESELBE Quelle haben. Sonst driftet die frei tippbare Spalte gegen die
    Eingabefelder — und genau daran krankte NET-13."""

    def setUp(self):
        self._orig_state = oc.get_state
        oc.get_state = lambda: _FakeState()

    def tearDown(self):
        oc.get_state = self._orig_state

    def test_spinbox_ranges_sind_die_bereiche(self):
        dlg = oc.OutputConfigDialog()
        try:
            self.assertEqual(
                (dlg._spin_artnet_start_univ.minimum(),
                 dlg._spin_artnet_start_univ.maximum()),
                oc._ext_universe_bereich("ArtNet"))
            self.assertEqual(
                (dlg._spin_sacn_in_univ.minimum(),
                 dlg._spin_sacn_in_univ.maximum()),
                oc._ext_universe_bereich("sACN"))
        finally:
            dlg.deleteLater()

    def test_spinboxen_folgen_der_quelle_wirklich(self):
        """★★ Der Unterschied zwischen „gleiche Zahl" und „gleiche Quelle":
        wird die Tabelle geaendert, muss die Spinbox mitgehen. Ein wieder fest
        eingetragenes ``setRange(0, 32767)`` faellt hier durch."""
        orig = dict(oc._EXT_UNIVERSE_BEREICHE)
        try:
            oc._EXT_UNIVERSE_BEREICHE["ArtNet"] = (2, 999)
            oc._EXT_UNIVERSE_BEREICHE["sACN"] = (3, 888)
            dlg = oc.OutputConfigDialog()
            try:
                self.assertEqual((dlg._spin_artnet_start_univ.minimum(),
                                  dlg._spin_artnet_start_univ.maximum()), (2, 999))
                self.assertEqual((dlg._spin_sacn_in_univ.minimum(),
                                  dlg._spin_sacn_in_univ.maximum()), (3, 888))
                # und der Guard der Spalte antwortet aus derselben Tabelle
                self.assertEqual(oc._coerce_ext_universe("5000", "ArtNet"), (999, True))
            finally:
                dlg.deleteLater()
        finally:
            oc._EXT_UNIVERSE_BEREICHE.clear()
            oc._EXT_UNIVERSE_BEREICHE.update(orig)

    def test_artnet_input_spinbox_bleibt_wie_sie_war(self):
        """Gegenprobe zur Reichweite: das Art-Net-INPUT-Feld beantwortet eine
        andere Frage (was hoere ich AB?) und laeuft heute ab 1. Es hier
        mitzuziehen haette seine Untergrenze nebenbei auf 0 verschoben."""
        dlg = oc.OutputConfigDialog()
        try:
            self.assertEqual((dlg._spin_artnet_in_univ.minimum(),
                              dlg._spin_artnet_in_univ.maximum()), (1, 32767))
        finally:
            dlg.deleteLater()


class TestGrenzenAmSendepfadGemessen(unittest.TestCase):
    """Warum GENAU diese Zahlen — an den echten Paketbauern nachgerechnet, nicht
    aus einer Norm abgeschrieben."""

    def test_grenzen_sind_am_sendepfad_gemessen(self):
        import struct
        from src.core.dmx.artnet import _build_artdmx
        from src.core.dmx.sacn import _pack_framing

        daten = bytes(512)
        art_max = oc._ext_universe_bereich("ArtNet")[1]
        # Die Obergrenze kommt heil an ...
        pkt = _build_artdmx(art_max, daten, 0)
        feld = struct.unpack_from("<H", pkt, 14)[0]
        self.assertEqual(feld & 0x7FFF, art_max)
        self.assertEqual(feld, art_max)
        # ... der Wert, den ein pauschales 1..63999 durchgelassen haette, nicht:
        feld40k = struct.unpack_from("<H", _build_artdmx(40000, daten, 0), 14)[0]
        self.assertEqual(feld40k & 0x7FFF, 7232)     # anderes Rig, ohne Meldung
        # ... und alles ueber 16 Bit sprengt das Feld ueberhaupt (je Frame).
        with self.assertRaises(struct.error):
            _build_artdmx(70000, daten, 0)

        sacn_max = oc._ext_universe_bereich("sACN")[1]

        def _framing(u):
            return _pack_framing(bytes(513), u, 0, "x", b"\0" * 16, 100)

        # Den Offset des Universe-Feldes MESSEN statt ihn zu behaupten: eine
        # falsch geratene Zahl liest sonst irgendein anderes Byte und der Test
        # erreicht seinen Gegenstand nie (er ist erst daran aufgefallen).
        a, b = _framing(1), _framing(2)
        abweichend = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertEqual(len(abweichend), 1, "Universe-Feld nicht eindeutig gefunden")
        off = abweichend[0] - 1                      # High-Byte davor
        self.assertEqual(struct.unpack_from("!H", a, off)[0], 1)

        self.assertEqual(struct.unpack_from("!H", _framing(sacn_max), off)[0],
                         sacn_max)
        # 70000 verschwindet still im Modulo — genau der gemeldete Befund.
        self.assertEqual(struct.unpack_from("!H", _framing(70000), off)[0], 4464)


# ── Teil 3: der echte Speicherpfad des Dialogs ──────────────────────────────

class _FakeState:
    """Nur was ``_univ_save`` und der Dialog-Bau brauchen."""

    def __init__(self):
        self.universes: dict = {}
        self.output_manager = None
        self.applied = 0

    def apply_output_config(self):
        self.applied += 1


class _MeldungsBox:
    """Nimmt die Dialoge auf, statt sie zu zeigen (Titel + Text je Aufruf)."""

    def __init__(self):
        self.meldungen: list[tuple[str, str, str]] = []

    def information(self, _p, titel, text, *a, **kw):
        self.meldungen.append(("info", titel, text))

    def warning(self, _p, titel, text, *a, **kw):
        self.meldungen.append(("warn", titel, text))

    def critical(self, _p, titel, text, *a, **kw):
        self.meldungen.append(("crit", titel, text))

    def titel(self) -> list[str]:
        return [t for _art, t, _txt in self.meldungen]

    def ext_meldungen(self) -> list[str]:
        return [txt for art, t, txt in self.meldungen
                if art == "warn" and t == "Externe Universe-Nummer angepasst"]


class TestSpeichernMitGuard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._pfad = os.path.join(self._tmp.name, "universes.json")
        self._orig_pfad = oc._UNIV_CONFIG_PATH
        self._orig_state = oc.get_state
        self._orig_box = oc.QMessageBox
        oc._UNIV_CONFIG_PATH = self._pfad
        self.state = _FakeState()
        oc.get_state = lambda: self.state
        self.box = _MeldungsBox()
        oc.QMessageBox = self.box
        self.dlg = oc.OutputConfigDialog()

    def tearDown(self):
        oc._UNIV_CONFIG_PATH = self._orig_pfad
        oc.get_state = self._orig_state
        oc.QMessageBox = self._orig_box
        self.dlg.deleteLater()
        self._tmp.cleanup()

    def _fuelle(self, zeilen: list[tuple[str, str]]):
        """zeilen = [(Ausgabetyp, Ext-Text)] -> Tabelle bauen, Vorbedingung sichern."""
        t = self.dlg._univ_table
        t.setRowCount(len(zeilen))
        for i, (typ, ext) in enumerate(zeilen):
            t.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            t.setItem(i, 1, QTableWidgetItem(f"U{i + 1}"))
            combo = t.cellWidget(i, 2)
            if combo is None:
                combo = QComboBox()
                for opt in ("Disabled", "Enttec", "sACN", "ArtNet"):
                    combo.addItem(opt)
                t.setCellWidget(i, 2, combo)
            combo.setCurrentText(typ)
            t.setItem(i, 3, QTableWidgetItem(""))
            t.setItem(i, 4, QTableWidgetItem(ext))
        # Hausregel 2: die Sonde muss ihren Gegenstand nachweislich erreichen.
        for i, (typ, ext) in enumerate(zeilen):
            assert t.cellWidget(i, 2).currentText() == typ, f"Zeile {i}: Typ nicht gesetzt"
            assert t.item(i, 4).text() == ext, f"Zeile {i}: Ext-Feld nicht gesetzt"
        return t

    def _speichern_und_lesen(self) -> list[dict]:
        self.box.meldungen.clear()
        self.dlg._univ_save()
        self.assertTrue(os.path.exists(self._pfad), "Datei wurde gar nicht geschrieben")
        with open(self._pfad, encoding="utf-8") as f:
            rows = json.load(f)
        # Der gemessene Pfad wurde wirklich durchlaufen (nicht vorher abgebrochen).
        self.assertIn("Gespeichert", self.box.titel())
        self.assertEqual(self.state.applied, 1)
        return rows

    # ── Drei Luecken, die die Mutationsprobe des Skeptikers aufgedeckt hat ──
    #
    # Alle drei Mutationen ueberlebten die erste Testfassung, obwohl der Code
    # jeweils das Richtige tat: was niemand festhaelt, kann jeder Aufraeumer
    # spaeter wegkuerzen.

    def test_die_meldung_nennt_JEDE_geklemmte_zeile(self):
        """★★★ Mutation, die ueberlebte: nur die ERSTE geklemmte Zeile melden.
        Alle Tests blieben gruen, weil sie nur `len(ext_meldungen()) == 1`
        pruefen — und das ist bei EINER zusammengefassten Meldung immer 1.
        Betriebsfolge: wer fuenf Zeilen vertippt, erfaehrt von einer."""
        self._fuelle([("sACN", "70000"), ("ArtNet", "40000"), ("sACN", "0")])
        rows = self._speichern_und_lesen()
        self.assertEqual([r.get("out_universe") for r in rows], [63999, 32767, 1])
        text = self.box.ext_meldungen()[0]
        for zeile in ("Zeile 1", "Zeile 2", "Zeile 3"):
            self.assertIn(zeile, text, f"{zeile} fehlt in der Meldung: {text!r}")

    def test_die_meldung_nennt_den_bereich_der_JEWEILIGEN_zeile(self):
        """★★ Mutation, die ueberlebte: die Bereichsliste fest auf sACN
        verdrahten. Eine Art-Net-Zeile bekaeme dann die Begruendung
        'muss zum Ausgabetyp passen (sACN 1..63999)' und daneben
        'Zeile 1 (ArtNet): 40000 → 32767' — eine Zahl, die zur genannten
        Grenze nicht passt. Der einzige Texttest lief auf einer sACN-Zeile."""
        self._fuelle([("ArtNet", "40000")])
        self._speichern_und_lesen()
        text = self.box.ext_meldungen()[0]
        # ★ Auf den BEREICHS-Text pruefen, nicht auf die blosse Zahl: "32767"
        # und "ArtNet" stehen ohnehin im Zeilenteil ("Zeile 1 (ArtNet): 40000 →
        # 32767"), und "63999" steht auch in einer fest verdrahteten
        # sACN-Begruendung. Die erste Fassung dieses Tests konnte die Mutation
        # deshalb nicht sehen — sie las Zeichen, die beide Fassungen enthalten.
        self.assertIn("ArtNet 0..32767", text,
                      f"die Begruendung nennt den Art-Net-Bereich nicht: {text!r}")
        self.assertIn("sACN 1..63999", text,
                      "beide Bereiche gehoeren genannt, sonst sieht die Grenze "
                      "willkuerlich aus")

    def test_eine_unparsebare_eingabe_laesst_die_zelle_in_ruhe(self):
        """★ Mutation, die ueberlebte: `ext_item.setText(...)` eine Ebene hoeher
        gezogen (ein voellig plausibler Refactor). Danach steht bei 'abc'
        woertlich `None` in der Zelle. Kein Test sah die ZELLE fuer
        unparsebare Eingaben an — nur die Datei."""
        self._fuelle([("sACN", "abc")])
        rows = self._speichern_und_lesen()
        self.assertNotIn("out_universe", rows[0])
        self.assertEqual(self.dlg._univ_table.item(0, 4).text(), "abc",
                         "die Eingabe des Bedieners wurde ueberschrieben")
        self.assertEqual(self.box.ext_meldungen(), [],
                         "leer/Muell meldet weiterhin nichts")

    def test_ungueltiger_wert_landet_nicht_mehr_in_der_datei(self):
        """Der Befund selbst: vorher stand hier 70000 in der Datei, bei genau
        EINER Meldung ('info','Gespeichert')."""
        self._fuelle([("sACN", "70000")])
        rows = self._speichern_und_lesen()
        self.assertEqual(rows[0]["out_universe"], 63999)
        self.assertEqual(len(self.box.ext_meldungen()), 1)
        text = self.box.ext_meldungen()[0]
        self.assertIn("70000", text)      # was getippt war
        self.assertIn("63999", text)      # was jetzt gilt
        self.assertIn("sACN", text)       # warum diese Grenze
        self.assertIn("Zeile 1", text)    # wo

    def test_artnet_zeile_wird_an_der_artnet_grenze_gemessen(self):
        """★ Die Zeile, die ein pauschales 1..63999 durchgelassen haette."""
        self._fuelle([("ArtNet", "40000")])
        rows = self._speichern_und_lesen()
        self.assertEqual(rows[0]["out_universe"], 32767)
        self.assertEqual(len(self.box.ext_meldungen()), 1)

    def test_gueltige_werte_bleiben_unveraendert_und_stumm(self):
        """★★ Die wichtigste Gegenprobe: ein Guard, der immer meldet, meldet
        nichts. Alle vier Randwerte gehen unangetastet durch — und die einzige
        Meldung ist die bisherige Erfolgsmeldung."""
        self._fuelle([("ArtNet", "0"), ("ArtNet", "32767"),
                      ("sACN", "1"), ("sACN", "63999")])
        rows = self._speichern_und_lesen()
        self.assertEqual([r["out_universe"] for r in rows], [0, 32767, 1, 63999])
        self.assertEqual(self.box.ext_meldungen(), [])
        t = self.dlg._univ_table
        self.assertEqual([t.item(i, 4).text() for i in range(4)],
                         ["0", "32767", "1", "63999"])

    def test_leeres_und_unparsebares_feld_verhalten_sich_wie_bisher(self):
        """Gegenprobe: kein neues Geraeusch fuer die Faelle, die schon vorher
        still auf den Default fielen."""
        self._fuelle([("sACN", ""), ("ArtNet", "abc")])
        rows = self._speichern_und_lesen()
        for r in rows:
            self.assertNotIn("out_universe", r)
        self.assertEqual(self.box.ext_meldungen(), [])

    def test_enttec_und_disabled_verlieren_ihre_nummer_nicht(self):
        """Gegenprobe zur sicheren Richtung: diese Zeilen haben gar kein externes
        Universum — der Wert wirkt nirgends, wird aber auch nicht stillschweigend
        aus der Datei entfernt."""
        self._fuelle([("Enttec", "7"), ("Disabled", "70000")])
        rows = self._speichern_und_lesen()
        self.assertEqual(rows[0]["out_universe"], 7)
        self.assertEqual(rows[1]["out_universe"], 70000)
        self.assertEqual(self.box.ext_meldungen(), [])

    def test_zelle_spiegelt_den_gespeicherten_wert(self):
        """Wie in der '#'-Spalte: was in der Datei steht, steht danach auch in
        der Tabelle — sonst zeigt der Dialog etwas anderes, als er gesichert hat."""
        t = self._fuelle([("ArtNet", "70000")])
        rows = self._speichern_und_lesen()
        self.assertEqual(t.item(0, 4).text(), "32767")
        self.assertEqual(str(rows[0]["out_universe"]), t.item(0, 4).text())

    def test_geklemmter_wert_geht_in_die_doppelziel_pruefung_ein(self):
        """Die Reihenfolge ist Teil der Aussage: erst klemmen, dann auf doppelte
        Ziele pruefen. Zwei Art-Net-Zeilen mit 40000 und 70000 landen BEIDE auf
        32767 — die Kollision entsteht erst durch das Klemmen und muss trotzdem
        gemeldet werden."""
        self._fuelle([("ArtNet", "40000"), ("ArtNet", "70000")])
        rows = self._speichern_und_lesen()
        self.assertEqual([r["out_universe"] for r in rows], [32767, 32767])
        self.assertIn("Zwei Universen auf demselben Ziel", self.box.titel())

    def test_nummern_spalte_und_ext_spalte_melden_getrennt(self):
        """Beide Guards greifen in derselben Zeile, ohne sich zu verschlucken:
        '#' = 70000 -> 32 (A3D-33), Ext = 70000 -> 63999 (NET-13)."""
        t = self._fuelle([("sACN", "70000")])
        t.item(0, 0).setText("70000")
        rows = self._speichern_und_lesen()
        self.assertEqual(rows[0]["num"], 32)
        self.assertEqual(rows[0]["out_universe"], 63999)
        self.assertIn("Universe-Nummer angepasst", self.box.titel())
        self.assertEqual(len(self.box.ext_meldungen()), 1)


if __name__ == "__main__":
    unittest.main()


# ─────────────────────────────────────────────────────────────────────────────
# ★★★ Vom Skeptiker gefunden: der ZWEITE Schreibweg.
#
# Die erste Fassung prüfte nur die Eingabe im Universe-Manager. Gemessen wurde
# aber ein Weg, der dieselbe Datei OHNE Guard schrieb: eine Zeile steht als
# ``Disabled`` mit ``out_universe: 70000`` in der Datei (ein Wert, den die
# Klemmung dort bewusst stehen lässt), der Bediener schaltet sie über den
# sACN-Tab scharf — ``_apply_sacn`` ruft ``_persist_output`` mit ``_UNSET``, der
# Wert wird also gar nicht neu geschrieben und bleibt ungeprüft stehen.
# Ergebnis: ``sACN`` mit ``out_universe: 70000``, keine Meldung, Statuszeile
# meldet „Aktiv". Im Paket landet 70000 & 0xFFFF = 4464.
#
# Die Begründung im Code lautete wörtlich „nach dem Zurückschalten auf sACN
# greift der Guard" — sie galt nur für einen der beiden Wege. Genau die Klasse,
# die uns heute schon dreimal getroffen hat: eine Regel, die einen zweiten
# Schreiber nicht kennt.
# ─────────────────────────────────────────────────────────────────────────────

class DieDateiEnthaeltNieEinenUngueltigenWertTest(unittest.TestCase):
    """Die Zusicherung liegt auf der DATEI, nicht auf der Eingabemaske."""

    def _zeile(self, output, out_universe):
        from src.ui.widgets import output_config as oc
        return oc._ext_zeile_pruefen({"num": 3, "name": "U3",
                                      "output": output, "patch": "",
                                      "out_universe": out_universe})

    def test_der_ECHTE_schreibweg_klemmt_mit(self):
        """★★★ Der Test, der den Skeptiker-Fund wirklich einzaeunt — und den ich
        zuerst vergessen hatte.

        Die Tests unten rufen ``_ext_zeile_pruefen`` DIREKT auf. Damit laesst
        sich der Aufruf aus ``_persist_output`` ersatzlos entfernen, ohne dass
        etwas rot wird: die Probe erreicht den Pfad nicht, den sie absichert.
        Genau das ist der gemessene Fall — eine ``Disabled``-Zeile mit 70000,
        die der sACN-Tab ueber ``_persist_output(..., _UNSET)`` scharf schaltet,
        ohne die Nummer neu zu schreiben."""
        import json as _json
        import tempfile as _tempfile
        with _tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            with open(pfad, "w", encoding="utf-8") as f:
                _json.dump([{"num": 3, "name": "U3", "output": "Disabled",
                             "patch": "", "out_universe": 70000}], f)
            orig = oc._UNIV_CONFIG_PATH
            oc._UNIV_CONFIG_PATH = pfad
            try:
                self.assertTrue(oc._persist_output(3, "sACN", "", oc._UNSET),
                                "Vorbedingung: die Datei wurde geschrieben")
                with open(pfad, encoding="utf-8") as f:
                    r = _json.load(f)[0]
            finally:
                oc._UNIV_CONFIG_PATH = orig
        self.assertEqual(r["output"], "sACN", "Vorbedingung: der Typ hat gewechselt")
        self.assertEqual(r["out_universe"], 63999,
                         "der zweite Schreibweg laesst 70000 stehen — im Paket "
                         "landet dann 70000 & 0xFFFF = 4464")

    def test_ein_gueltiger_wert_ueberlebt_den_echten_schreibweg(self):
        """Gegenprobe: der Guard im Schreibweg darf nichts anfassen, was passt."""
        import json as _json
        import tempfile as _tempfile
        with _tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            with open(pfad, "w", encoding="utf-8") as f:
                _json.dump([{"num": 2, "name": "U2", "output": "sACN",
                             "patch": "", "out_universe": 40000}], f)
            orig = oc._UNIV_CONFIG_PATH
            oc._UNIV_CONFIG_PATH = pfad
            try:
                oc._persist_output(2, "sACN", "", oc._UNSET)
                with open(pfad, encoding="utf-8") as f:
                    r = _json.load(f)[0]
            finally:
                oc._UNIV_CONFIG_PATH = orig
        self.assertEqual(r["out_universe"], 40000)

    def test_auch_eine_NEU_angelegte_zeile_wird_gemessen(self):
        """★ Die Zusicherung liegt auf ``_persist_output``, nicht auf seinen
        heutigen Aufrufern: *diese Datei enthaelt nie einen Wert ausserhalb des
        Bereichs ihres Typs*. Heute reichen alle Aufrufer nur bereichsgepruefte
        Spinbox-Werte herein, die Zeile waere also unerreichbar — und eine
        Mutation ueberlebte sie prompt. Ein Test macht aus der unerreichbaren
        Zeile eine zugesicherte."""
        import json as _json
        import tempfile as _tempfile
        with _tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            with open(pfad, "w", encoding="utf-8") as f:
                _json.dump([], f)
            orig = oc._UNIV_CONFIG_PATH
            oc._UNIV_CONFIG_PATH = pfad
            try:
                oc._persist_output(9, "ArtNet", "10.0.0.5", 70000)
                with open(pfad, encoding="utf-8") as f:
                    r = _json.load(f)[0]
            finally:
                oc._UNIV_CONFIG_PATH = orig
        self.assertEqual(r["num"], 9, "Vorbedingung: die Zeile wurde NEU angelegt")
        self.assertEqual(r["out_universe"], 32767)

    def test_ein_typwechsel_misst_die_stehengebliebene_nummer_nach(self):
        """★★★ Der Kern des Skeptiker-Fundes: die Nummer wird gar nicht neu
        geschrieben — sie war schon da. Geprüft wird trotzdem, weil sich der
        TYP geändert hat."""
        from src.ui.widgets import output_config as oc
        r = {"num": 3, "name": "U3", "output": "sACN", "patch": "",
             "out_universe": 70000}
        angepasst = oc._ext_zeile_pruefen(r)
        self.assertTrue(angepasst)
        self.assertEqual(r["out_universe"], 63999)

    def test_dieselbe_nummer_ist_je_nach_typ_gueltig_oder_nicht(self):
        """40000 ist für sACN erlaubt und für Art-Net nicht — die Zeile misst
        sich an ihrem eigenen Typ, nicht an einer pauschalen Grenze."""
        from src.ui.widgets import output_config as oc
        s = {"num": 1, "output": "sACN", "patch": "", "out_universe": 40000}
        a = {"num": 2, "output": "ArtNet", "patch": "", "out_universe": 40000}
        self.assertFalse(oc._ext_zeile_pruefen(s))
        self.assertEqual(s["out_universe"], 40000)
        self.assertTrue(oc._ext_zeile_pruefen(a))
        self.assertEqual(a["out_universe"], 32767)

    def test_enttec_und_disabled_behalten_ihren_wert(self):
        """Die Gegenprobe zur Durchreichung: ohne externes Universum gibt es
        keinen Bereich zum Messen. Der Wert bleibt stehen, statt still zu
        verschwinden — und wird geprüft, sobald die Zeile wieder einen Typ
        bekommt, der ihn benutzt (Test darüber)."""
        for typ in ("Enttec", "Disabled"):
            with self.subTest(typ=typ):
                r = {"num": 3, "output": typ, "patch": "", "out_universe": 70000}
                self.assertFalse(self._zeile(typ, 70000))
                from src.ui.widgets import output_config as oc
                oc._ext_zeile_pruefen(r)
                self.assertEqual(r["out_universe"], 70000)

    def test_ein_gueltiger_wert_bleibt_unangetastet(self):
        for typ, wert in (("ArtNet", 0), ("ArtNet", 32767),
                          ("sACN", 1), ("sACN", 63999)):
            with self.subTest(typ=typ, wert=wert):
                self.assertFalse(self._zeile(typ, wert))

    def test_eine_zeile_ohne_externe_nummer_bekommt_keine(self):
        """Kein Feld heisst Default — daraus darf nicht still eine 0 werden."""
        from src.ui.widgets import output_config as oc
        r = {"num": 1, "output": "ArtNet", "patch": ""}
        self.assertFalse(oc._ext_zeile_pruefen(r))
        self.assertNotIn("out_universe", r)

    def test_unparsebarer_altbestand_wird_entfernt_statt_zu_werfen(self):
        """Eine von Hand editierte Datei kann alles enthalten. Ein Absturz beim
        Speichern wäre die schlechteste Antwort darauf."""
        from src.ui.widgets import output_config as oc
        r = {"num": 1, "output": "sACN", "patch": "", "out_universe": "abc"}
        self.assertFalse(oc._ext_zeile_pruefen(r))
        self.assertNotIn("out_universe", r)
