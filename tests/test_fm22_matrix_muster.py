"""FM-22 — Muster fuer ein Matrix-Panel in der UI bauen statt im Skript.

Ausgangslage (Robin, 2026-08-05): die Demo-Show mit Spalten-/Reihen-Lauflichtern
liess sich NUR per Build-Skript erzeugen. Zwei Luecken, beide hier geprueft:

**(1) Das Raster.** Ein Matrix-Effekt bezog sein Raster ausschliesslich aus einer
Fixture-Gruppe — fuer ein 48-Zonen-Panel hiess das Gruppen-Tab, Raster
vergroessern, Geraet finden, aufteilen, zurueck. Neu: ``panel_grid`` +
``PanelGridDialog`` + der Knopf „Raster aus Gerät" in der Matrix-View.

**(2) Die Muster.** Ein Lauflicht „Spalte fuer Spalte" war nur als Chaser aus 12
von Hand angelegten Szenen baubar. Neu: ``pattern_frames`` +
``build_pattern_chaser`` + der Muster-Assistent.

★ Der schaerfste Test hier ist ``ReferenzGleichheitTest``: die erzeugten Schritte
werden gegen die Zellen gehalten, die ``tools/build_zq06121_demo.py`` von Hand
aufzaehlt. Das ist die eigentliche Behauptung des Items — „was im Skript steht,
soll in der UI in wenigen Klicks entstehen" —, und sie ist nur dann belegt, wenn
beide Wege DASSELBE liefern.

Die Dialoge werden gebaut und bedient (Combo umschalten, Spinbox drehen, Knopf
klicken), nicht auf Quelltext geprueft.
"""
import os
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog     # noqa: E402

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets   # noqa: E402

import src.core.app_state as A                            # noqa: E402
from src.core.matrix_pattern import (                     # noqa: E402
    PATTERN_DIRECTIONS, band_count, build_pattern_chaser, cell_channel_values,
    direction_label, panel_grid, pattern_frames, suggested_block_cols)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


# ── Testgeraete ──────────────────────────────────────────────────────────────

class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0


def _panel_channels(zonen, *, master=True):
    """Ein Panel wie der ZQ06121: EIN Master-Dimmer, dann je Zone R/G/B."""
    chans, k = [], 1
    if master:
        chans.append(_Ch("intensity", k))
        k += 1
    for _z in range(zonen):
        for a in ("color_r", "color_g", "color_b"):
            chans.append(_Ch(a, k))
            k += 1
    return chans


def _hydra_channels(koepfe):
    """Ein Geraet mit GETEILTEM Master-Dimmer UND kopfeigenen Dimmern
    (Hydrabeam-Bauart, FM-17): CH1 ist der gemeinsame Master, danach je Kopf
    R/G/B + eigener Dimmer. Genau hier greift die Kopf-Karte — und genau hier
    reicht ``channels_for_head`` allein NICHT."""
    chans = [_Ch("intensity", 1)]
    k = 2
    for _h in range(koepfe):
        for a in ("color_r", "color_g", "color_b", "intensity"):
            chans.append(_Ch(a, k))
            k += 1
    return chans


def _fx(fid=7, label="LED-Balken", **kw):
    return NS(fid=fid, label=label, universe=1, address=1,
              fixture_type=kw.pop("fixture_type", "par"),
              pixel_order=kw.pop("pixel_order", "rowwise"),
              element_rotation=kw.pop("element_rotation", 0),
              element_flip=kw.pop("element_flip", False), **kw)


class _ChannelPatch:
    """Haengt ``get_channels_for_patched`` an eine Tabelle fid -> Kanaele.

    Stubbt die DATENBANK, nicht die Rechnung: ``color_head_count`` und
    ``channels_for_head`` laufen echt darueber.
    """

    def __init__(self, table):
        self._table = table
        self._orig = A.get_channels_for_patched

    def __enter__(self):
        A.get_channels_for_patched = lambda fx: self._table[getattr(fx, "fid")]
        return self

    def __exit__(self, *exc):
        A.get_channels_for_patched = self._orig
        return False


# ── (1) Das Raster ───────────────────────────────────────────────────────────

class PanelRasterTest(unittest.TestCase):
    """``panel_grid``: Koepfe eines Geraets -> fertiges Matrix-Raster."""

    def test_48_zonen_als_12x4(self):
        cols, rows, cells = panel_grid(48, 12)
        self.assertEqual((cols, rows), (12, 4))
        self.assertEqual(cells[:12], list(range(12)))
        self.assertEqual(cells[12], 12)          # zweite Zeile beginnt bei 12
        self.assertEqual(len(cells), 48)
        self.assertIsNone(next((c for c in cells if c is None), None))

    def test_angebrochene_letzte_zeile_gibt_luecken(self):
        # 50 Koepfe auf 12 Spalten = 5 Zeilen, davon die letzte halb leer.
        cols, rows, cells = panel_grid(50, 12)
        self.assertEqual((cols, rows), (12, 5))
        self.assertEqual(len(cells), 60)
        self.assertEqual(sum(1 for c in cells if c is None), 10)
        # Die vorhandenen Koepfe stehen VORN in der letzten Zeile, nicht verteilt.
        self.assertEqual(cells[48], 48)
        self.assertEqual(cells[49], 49)
        self.assertIsNone(cells[50])

    def test_schlangenlinien_kehren_jede_zweite_zeile_um(self):
        _c, _r, cells = panel_grid(16, 4, order="serpentine")
        self.assertEqual(cells[:4], [0, 1, 2, 3])
        self.assertEqual(cells[4:8], [7, 6, 5, 4])

    def test_montage_hochkant_dreht_das_raster(self):
        """90° tauscht Zeilen und Spalten — aus 12x4 wird 4x12."""
        cols, rows, cells = panel_grid(48, 12, rotation=90)
        self.assertEqual((cols, rows), (4, 12))
        self.assertEqual(len(cells), 48)
        # Kopf 0 sitzt hochkant oben rechts (Spalte 3 der ersten Zeile).
        self.assertEqual(cells[3], 0)
        self.assertEqual(cells[0], 36)

    def test_spiegelung_kehrt_die_spalten_um(self):
        _c, _r, cells = panel_grid(12, 12, flip=True)
        self.assertEqual(cells, list(range(11, -1, -1)))

    def test_unsinnige_eingabe_liefert_leeres_raster(self):
        for args in ((0, 12), (48, 0), (-3, 4), ("x", 4)):
            self.assertEqual(panel_grid(*args), (0, 0, []),
                             f"panel_grid{args} sollte leer sein")

    def test_spaltenvorschlag_ist_teiler_nahe_der_wurzel(self):
        self.assertEqual(suggested_block_cols(48), 6)      # nicht 7
        self.assertEqual(48 % suggested_block_cols(48), 0)
        self.assertEqual(suggested_block_cols(16), 4)
        # Primzahl: kein echter Teiler -> die Zahl selbst (eine Zeile).
        self.assertEqual(suggested_block_cols(13), 13)
        self.assertEqual(suggested_block_cols(1), 1)


# ── (2) Die Muster ───────────────────────────────────────────────────────────

class MusterTest(unittest.TestCase):

    def test_baenderzahl_je_richtung(self):
        self.assertEqual(band_count(12, 4, "spalten_lr"), 12)
        self.assertEqual(band_count(12, 4, "reihen_ou"), 4)
        # Diagonalen eines 12x4-Rasters: 15, nicht 16.
        self.assertEqual(band_count(12, 4, "diagonal_lo"), 15)
        self.assertEqual(band_count(0, 4, "spalten_lr"), 0)

    def test_spalten_lauflicht_ein_schritt_je_spalte(self):
        frames = pattern_frames(12, 4, "spalten_lr")
        self.assertEqual(len(frames), 12)
        self.assertEqual(frames[0], [0, 12, 24, 36])
        self.assertEqual(frames[11], [11, 23, 35, 47])

    def test_rueckwaerts_ist_die_umgekehrte_folge(self):
        vor = pattern_frames(12, 4, "spalten_lr")
        zurueck = pattern_frames(12, 4, "spalten_rl")
        self.assertEqual(zurueck, list(reversed(vor)))
        self.assertNotEqual(zurueck, vor)

    def test_reihen_lauflicht(self):
        frames = pattern_frames(4, 3, "reihen_ou")
        self.assertEqual(frames, [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]])
        self.assertEqual(pattern_frames(4, 3, "reihen_uo"),
                         list(reversed(frames)))

    def test_diagonale_laeuft_von_links_oben(self):
        frames = pattern_frames(4, 3, "diagonal_lo")
        self.assertEqual(len(frames), 6)
        self.assertEqual(frames[0], [0])            # nur die Ecke links oben
        self.assertEqual(frames[1], [1, 4])
        self.assertEqual(frames[-1], [11])          # Ecke rechts unten

    def test_gegendiagonale_startet_rechts_oben(self):
        """``diagonal_ro`` ist NICHT die zeitliche Umkehr von ``diagonal_lo`` —
        es ist die andere Achse. Ohne diesen Test waere ein vertauschtes
        Band-Mass unsichtbar, weil beide 6 Schritte haben."""
        frames = pattern_frames(4, 3, "diagonal_ro")
        self.assertEqual(len(frames), 6)
        self.assertEqual(frames[0], [3])            # Ecke rechts oben
        self.assertEqual(frames[-1], [8])           # Ecke links unten
        self.assertNotEqual(frames, list(reversed(pattern_frames(4, 3, "diagonal_lo"))))

    def test_breiter_balken_leuchtet_umlaufend_gleich_breit(self):
        frames = pattern_frames(4, 2, "spalten_lr", width=2)
        self.assertEqual(len(frames), 4)
        for f in frames:
            self.assertEqual(len(f), 4, f"Balken wechselt die Breite: {f}")
        self.assertEqual(frames[0], [0, 1, 4, 5])
        # Letzter Schritt laeuft ueber den Rand zurueck auf Spalte 0.
        self.assertEqual(frames[3], [0, 3, 4, 7])

    def test_balken_breiter_als_die_flaeche_wird_geklemmt(self):
        """POSITIVKONTROLLE gleich mit: Breite 3 auf 4 Spalten bleibt Breite 3."""
        normal = pattern_frames(4, 2, "spalten_lr", width=3)
        self.assertEqual(len(normal[0]), 6)          # 3 Spalten x 2 Zeilen
        zu_breit = pattern_frames(4, 2, "spalten_lr", width=9)
        for f in zu_breit:
            self.assertEqual(len(f), 8)              # alles an, aber nicht mehr
            self.assertEqual(f, sorted(set(f)), "Zelle doppelt im Schritt")

    def test_leeres_raster_liefert_keine_schritte(self):
        self.assertEqual(pattern_frames(0, 4, "spalten_lr"), [])
        self.assertEqual(pattern_frames(4, 0, "reihen_ou"), [])

    def test_richtungsbeschriftungen_vollstaendig(self):
        for key, label in PATTERN_DIRECTIONS:
            self.assertEqual(direction_label(key), label)
            self.assertTrue(pattern_frames(5, 3, key),
                            f"Richtung {key} liefert keine Schritte")
        self.assertEqual(direction_label("gibtsnicht"), "gibtsnicht")


class ReferenzGleichheitTest(unittest.TestCase):
    """Der Kern des Items: UI-Weg == Skript-Weg.

    ``tools/build_zq06121_demo.py`` zaehlt die Zellen von Hand auf::

        spalten = [[zone(r, c) for r in range(4)] for c in range(12)]
        reihen  = [[zone(r, c) for c in range(12)] for r in range(4)]

    Genau diese Listen muss der Assistent erzeugen — sonst laeuft der Balken in
    der UI anders als in der Demo, und niemand koennte sagen welcher stimmt.
    """

    SPALTEN, REIHEN = 12, 4

    def _zone(self, r, c):
        return r * self.SPALTEN + c

    def test_raster_wie_im_skript(self):
        cols, rows, cells = panel_grid(48, self.SPALTEN)
        self.assertEqual((cols, rows), (self.SPALTEN, self.REIHEN))
        self.assertEqual(cells, list(range(48)))     # head_grid = 0..47

    def test_spalten_wie_im_skript(self):
        ref = [sorted(self._zone(r, c) for r in range(self.REIHEN))
               for c in range(self.SPALTEN)]
        self.assertEqual(pattern_frames(self.SPALTEN, self.REIHEN,
                                        "spalten_lr"), ref)

    def test_reihen_wie_im_skript(self):
        ref = [sorted(self._zone(r, c) for c in range(self.SPALTEN))
               for r in range(self.REIHEN)]
        self.assertEqual(pattern_frames(self.SPALTEN, self.REIHEN,
                                        "reihen_ou"), ref)


# ── (3) Aus Mustern werden Szenen + Chaser ───────────────────────────────────

class ZellenKanaeleTest(unittest.TestCase):

    def test_kopf_bekommt_seine_eigenen_farbkanaele(self):
        chans = _panel_channels(48)
        with _ChannelPatch({7: chans}):
            vals = cell_channel_values(_fx(), 0, (255, 0, 0))
            self.assertEqual(vals.get(2), 255)       # Zone 0 rot  = CH2
            self.assertEqual(vals.get(3), 0)
            vals2 = cell_channel_values(_fx(), 5, (0, 0, 255))
            self.assertEqual(vals2.get(19), 255)     # Zone 5 blau = CH19
            self.assertNotIn(2, {k for k in vals2 if k in (2, 3, 4)})

    def test_gemeinsamer_master_dimmer_kommt_mit(self):
        """Ohne den bleibt das Geraet STOCKDUNKEL, obwohl 144 Farbkanaele
        korrekt gesetzt sind — genau der Live-Test-Ausfall vom 2026-08-05."""
        chans = _panel_channels(48, master=True)
        with _ChannelPatch({7: chans}):
            vals = cell_channel_values(_fx(), 3, (255, 255, 255))
        self.assertEqual(vals.get(1), 255, "Master-Dimmer CH1 nicht hochgezogen")

    def test_geteilter_master_kommt_zusaetzlich_zum_kopf_dimmer_mit(self):
        """★ Der Fall, in dem ``channels_for_head`` allein zu wenig ist (FM-17).

        Hat das Geraet eine Kopf-Karte fuer den Dimmer, gehoert der geteilte
        Master KEINEM Kopf mehr — die Zelle zieht dann ihren eigenen Dimmer hoch
        und bleibt hinter dem gemeinsamen (Default 0) trotzdem dunkel. Der
        vorige Test kann das nicht zeigen: dort gibt es nur EINEN Dimmer, der
        ueber den normalen „einmaliges Attribut = geteilt"-Pfad ohnehin
        mitkommt.
        """
        chans = _hydra_channels(4)
        with _ChannelPatch({7: chans}):
            vals = cell_channel_values(_fx(), 2, (255, 0, 0))
        self.assertEqual(vals.get(1), 255, "gemeinsamer Master CH1 bleibt auf 0")
        self.assertEqual(vals.get(13), 255, "kopfeigener Dimmer nicht gesetzt")
        self.assertEqual(vals.get(10), 255)          # Kopf 2 rot = CH10

    def test_ohne_dimmer_option_bleibt_der_master_unberuehrt(self):
        """POSITIVKONTROLLE: der Dimmer wird nicht wahllos angefasst."""
        chans = _panel_channels(48, master=True)
        with _ChannelPatch({7: chans}):
            vals = cell_channel_values(_fx(), 3, (255, 255, 255),
                                       drive_intensity=False)
        self.assertNotIn(1, vals)
        self.assertTrue(any(v == 255 for v in vals.values()))

    def test_weiss_laeuft_nicht_mit(self):
        """Robin, 2026-08-05: Weiss soll bei Farbeffekten NICHT mitlaufen."""
        chans = _panel_channels(4)
        chans.append(_Ch("color_w", 99))
        with _ChannelPatch({7: chans}):
            vals = cell_channel_values(_fx(), 0, (255, 255, 255))
        self.assertNotIn(99, vals)

    def test_zelle_ohne_kopf_faerbt_das_ganze_geraet(self):
        chans = _panel_channels(2)
        with _ChannelPatch({7: chans}):
            vals = cell_channel_values(_fx(), None, (10, 20, 30))
        self.assertEqual(vals.get(2), 10)
        self.assertEqual(vals.get(5), 10)            # zweite Zone auch


class ChaserBauTest(unittest.TestCase):

    def setUp(self):
        from src.core.engine.function_manager import get_function_manager
        self.fm = get_function_manager()
        self._pre = {f.id for f in self.fm.all()}

    def tearDown(self):
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def _matrix(self, zonen=48, cols=12, rows=4, fid=7):
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance("Panel", cols=cols, rows=rows)
        m.fixture_grid = [fid] * zonen
        m.head_grid = list(range(zonen))
        return m

    def test_ein_schritt_je_spalte_mit_harter_kante(self):
        m = self._matrix()
        frames = pattern_frames(12, 4, "spalten_lr")
        with _ChannelPatch({7: _panel_channels(48)}):
            ch, szenen = build_pattern_chaser(
                self.fm, m, frames, name="Bars", color=(255, 255, 255),
                hold=0.12, patch_cache=[_fx()])
        self.assertIsNotNone(ch)
        self.assertEqual(len(szenen), 12)
        self.assertEqual(len(ch.steps), 12)
        for st in ch.steps:
            self.assertEqual(st.fade_in, 0.0)
            self.assertEqual(st.fade_out, 0.0)
            self.assertAlmostEqual(st.hold, 0.12)
        # Schritt 1 faerbt genau die vier Zonen der ersten Spalte rot/gruen/blau
        # + den Master — 4 Zonen x 3 Kanaele + 1 Dimmer.
        werte = {(v.channel, v.value) for v in szenen[0].values}
        self.assertEqual(len(werte), 13)
        self.assertIn((1, 255), werte)               # Master-Dimmer

    def test_szenen_und_chaser_landen_im_funktionsmanager(self):
        m = self._matrix()
        with _ChannelPatch({7: _panel_channels(48)}):
            ch, szenen = build_pattern_chaser(
                self.fm, m, pattern_frames(12, 4, "reihen_ou"), name="Reihen",
                patch_cache=[_fx()])
        ids = {f.id for f in self.fm.all()}
        self.assertIn(ch.id, ids)
        for sc in szenen:
            self.assertIn(sc.id, ids, "Szene nicht im FunctionManager")
        self.assertEqual([st.function_id for st in ch.steps],
                         [sc.id for sc in szenen])

    def test_schritte_liegen_in_einem_eigenen_ordner(self):
        """12 lose Szenen je Muster machen die Funktionsliste unbenutzbar."""
        m = self._matrix()
        with _ChannelPatch({7: _panel_channels(48)}):
            ch, szenen = build_pattern_chaser(
                self.fm, m, pattern_frames(12, 4, "spalten_lr"),
                name="Bars/Test", patch_cache=[_fx()])
        self.assertEqual({sc.folder for sc in szenen}, {"Bars-Test"})
        # Der Chaser selbst bleibt in der Wurzel: er ist das, was man startet.
        self.assertEqual(ch.folder, "")

    def test_leeres_raster_legt_nichts_an(self):
        m = self._matrix()
        m.fixture_grid = [None] * 48
        vorher = len(self.fm.all())
        ch, szenen = build_pattern_chaser(
            self.fm, m, pattern_frames(12, 4, "spalten_lr"), name="Leer",
            patch_cache=[_fx()])
        self.assertIsNone(ch)
        self.assertEqual(szenen, [])
        self.assertEqual(len(self.fm.all()), vorher,
                         "leerer Chaser im Funktionsbaum angelegt")

    def test_ohne_gepatchtes_geraet_legt_nichts_an(self):
        m = self._matrix()
        vorher = len(self.fm.all())
        ch, _ = build_pattern_chaser(self.fm, m,
                                     pattern_frames(12, 4, "spalten_lr"),
                                     name="Fremd", patch_cache=[])
        self.assertIsNone(ch)
        self.assertEqual(len(self.fm.all()), vorher)

    def test_dunkle_zellen_bleiben_ungeschrieben(self):
        """Der Chaser soll eine darunterliegende Ebene nicht ausknipsen."""
        m = self._matrix()
        with _ChannelPatch({7: _panel_channels(48)}):
            _ch, szenen = build_pattern_chaser(
                self.fm, m, pattern_frames(12, 4, "spalten_lr"), name="Bars",
                patch_cache=[_fx()])
        gesetzte = {v.channel for v in szenen[0].values}
        self.assertNotIn(5, gesetzte)                # Zone 1 (Spalte 2) = CH5


# ── Dialoge: bauen und bedienen ──────────────────────────────────────────────

class PanelGridDialogTest(unittest.TestCase):

    def setUp(self):
        _app()
        from src.ui.views.matrix_pattern_dialogs import panel_candidates
        self._cands = panel_candidates
        self.table = {7: _panel_channels(48), 8: _panel_channels(16),
                      9: _panel_channels(1)}
        self.fixtures = [_fx(7, "LED-Balken"), _fx(8, "Kleines Panel"),
                         _fx(9, "Einzel-PAR")]

    def test_nur_geraete_mit_mehreren_zonen_werden_angeboten(self):
        with _ChannelPatch(self.table):
            cands = self._cands(self.fixtures)
        fids = [c.fid for c in cands]
        self.assertIn(7, fids)                       # POSITIVKONTROLLE
        self.assertIn(8, fids)
        self.assertNotIn(9, fids, "1-Zonen-Geraet ergaebe ein 1x1-Raster")
        self.assertEqual(cands[0].head_count, 48)

    def test_montageangaben_kommen_aus_dem_patch(self):
        with _ChannelPatch({7: _panel_channels(48)}):
            c = self._cands([_fx(7, pixel_order="serpentine",
                                 element_rotation=90, element_flip=True)])[0]
        self.assertEqual(c.order, "serpentine")
        self.assertEqual(c.rotation, 90)
        self.assertTrue(c.flip)

    def _dialog(self):
        from src.ui.views.matrix_pattern_dialogs import PanelGridDialog
        with _ChannelPatch(self.table):
            cands = self._cands(self.fixtures)
        return PanelGridDialog(cands)

    def test_dialog_liefert_uebernehmbares_raster(self):
        dlg = self._dialog()
        dlg._cols_spin.setValue(12)
        cols, rows, fixture_grid, head_grid = dlg.result_grid()
        self.assertEqual((cols, rows), (12, 4))
        self.assertEqual(head_grid, list(range(48)))
        self.assertEqual(set(fixture_grid), {7})
        dlg.deleteLater()

    def test_geraetewechsel_setzt_den_spaltenvorschlag_neu(self):
        dlg = self._dialog()
        self.assertEqual(dlg._cols_spin.value(), suggested_block_cols(48))
        dlg._fix_combo.setCurrentIndex(1)            # 16 Zonen
        self.assertEqual(dlg._cols_spin.value(), suggested_block_cols(16))
        self.assertEqual(dlg.candidate().fid, 8)
        dlg.deleteLater()

    def test_luecken_steuern_kein_geraet_an(self):
        dlg = self._dialog()
        dlg._cols_spin.setValue(7)                   # 48 auf 7 Spalten = Rest
        cols, rows, fixture_grid, head_grid = dlg.result_grid()
        self.assertEqual((cols, rows), (7, 7))
        self.assertEqual(len(fixture_grid), 49)
        self.assertIsNone(head_grid[48])
        self.assertIsNone(fixture_grid[48],
                          "Luecke zeigt auf ein Geraet, das dort keinen Kopf hat")
        self.assertIn("Lücken", dlg._info.text())
        dlg.deleteLater()

    def test_infozeile_nennt_form_und_montage(self):
        dlg = self._dialog()
        dlg._cols_spin.setValue(12)
        text = dlg._info.text()
        self.assertIn("48 Zonen", text)
        self.assertIn("4 Reihen × 12 Spalten", text)
        self.assertNotIn("Lücken", text)             # POSITIVKONTROLLE
        dlg.deleteLater()

    def test_ohne_kandidaten_ist_uebernehmen_gesperrt(self):
        from src.ui.views.matrix_pattern_dialogs import PanelGridDialog
        leer = PanelGridDialog([])
        self.assertFalse(leer._ok_button.isEnabled())
        self.assertEqual(leer.result_grid(), (0, 0, [], []))
        voll = self._dialog()
        self.assertTrue(voll._ok_button.isEnabled())  # POSITIVKONTROLLE
        leer.deleteLater()
        voll.deleteLater()


class PatternWizardDialogTest(unittest.TestCase):

    def setUp(self):
        _app()
        from src.ui.views.matrix_pattern_dialogs import PatternWizardDialog
        self.dlg = PatternWizardDialog(12, 4, default_name="Bars")

    def tearDown(self):
        self.dlg.deleteLater()

    def test_bedienung_erzeugt_die_erwarteten_schritte(self):
        self.dlg._dir_combo.setCurrentIndex(0)       # Spalten links -> rechts
        self.assertEqual(self.dlg.direction(), "spalten_lr")
        self.assertEqual(self.dlg.frames(),
                         pattern_frames(12, 4, "spalten_lr"))
        self.dlg._dir_combo.setCurrentIndex(2)       # Reihen oben -> unten
        self.assertEqual(self.dlg.direction(), "reihen_ou")
        self.assertEqual(len(self.dlg.frames()), 4)

    def test_balkenbreite_wird_auf_die_baender_geklemmt(self):
        self.dlg._dir_combo.setCurrentIndex(2)       # Reihen: nur 4 Baender
        self.assertEqual(self.dlg._width_spin.maximum(), 4)
        self.dlg._dir_combo.setCurrentIndex(0)       # Spalten: 12 Baender
        self.assertEqual(self.dlg._width_spin.maximum(), 12)   # POSITIVKONTROLLE

    def test_tempo_wird_in_haltezeit_umgerechnet(self):
        self.dlg._tempo_spin.setValue(8.0)
        self.assertAlmostEqual(self.dlg.hold(), 0.125)
        self.dlg._tempo_spin.setValue(2.0)
        self.assertAlmostEqual(self.dlg.hold(), 0.5)
        self.assertAlmostEqual(self.dlg.result().hold, 0.5)

    def test_ergebnis_traegt_alle_vier_angaben(self):
        self.dlg._name_edit.setText("  Bars nacheinander  ")
        self.dlg._dir_combo.setCurrentIndex(1)
        self.dlg._width_spin.setValue(2)
        self.dlg.set_color((0, 160, 255))
        self.dlg._tempo_spin.setValue(4.0)
        res = self.dlg.result()
        self.assertEqual(res.name, "Bars nacheinander")
        self.assertEqual(res.direction, "spalten_rl")
        self.assertEqual(res.width, 2)
        self.assertEqual(res.color, (0, 160, 255))
        self.assertAlmostEqual(res.hold, 0.25)

    def test_leerer_name_faellt_auf_einen_vorgabenamen_zurueck(self):
        self.dlg._name_edit.setText("   ")
        self.assertEqual(self.dlg.result().name, "Lauflicht")

    def test_vorschau_zeigt_die_schritte_und_laeuft(self):
        self.dlg._dir_combo.setCurrentIndex(0)
        pv = self.dlg._preview
        self.assertEqual(pv.frames, pattern_frames(12, 4, "spalten_lr"))
        self.assertTrue(pv._timer.isActive())
        self.assertEqual(pv.current_cells(), [0, 12, 24, 36])
        pv.advance()
        self.assertEqual(pv.current_cells(), [1, 13, 25, 37])
        for _ in range(11):
            pv.advance()
        self.assertEqual(pv.index, 0, "Vorschau laeuft nicht im Kreis")

    def test_vorschau_malt_die_leuchtenden_zellen(self):
        """Nicht nur „die Zellen sind bekannt" — es wird auch gemalt.

        Gegen die Bildpunkte des echten Widgets geprueft: eine Vorschau, die die
        Schritte kennt und trotzdem schwarz bleibt, waere aus Sicht des Nutzers
        genauso kaputt wie gar keine.
        """
        from src.ui.views.matrix_pattern_dialogs import PatternPreview
        pv = PatternPreview()
        self.addCleanup(pv.deleteLater)
        pv.resize(120, 40)                           # 12 Spalten a 10 px breit
        pv.set_pattern(12, 4, pattern_frames(12, 4, "spalten_lr"),
                       (255, 255, 255))
        bild = pv.grab().toImage()
        an = bild.pixelColor(5, 5)                   # Spalte 0 = leuchtet
        aus = bild.pixelColor(15, 5)                 # Spalte 1 = dunkel
        self.assertEqual((an.red(), an.green(), an.blue()), (255, 255, 255))
        self.assertNotEqual((aus.red(), aus.green(), aus.blue()),
                            (255, 255, 255))
        pv.advance()                                 # Balken eine Spalte weiter
        bild2 = pv.grab().toImage()
        self.assertNotEqual(bild2.pixelColor(5, 5).rgb(), an.rgb())
        self.assertEqual(bild2.pixelColor(15, 5).rgb(), an.rgb())

    def test_vorschau_haelt_beim_schliessen_an(self):
        self.assertTrue(self.dlg._preview._timer.isActive())
        self.dlg.done(QDialog.DialogCode.Rejected)
        self.assertFalse(self.dlg._preview._timer.isActive())

    def test_infozeile_nennt_schritte_und_dauer(self):
        self.dlg._dir_combo.setCurrentIndex(0)
        self.dlg._tempo_spin.setValue(10.0)
        self.assertIn("12 Schritte", self.dlg._info.text())
        self.assertIn("100 ms", self.dlg._info.text())


# ── Die Knoepfe in der Matrix-View ───────────────────────────────────────────

class MatrixViewKnoepfeTest(unittest.TestCase):
    """Der echte Weg: Knopf druecken -> Dialog -> Raster bzw. Chaser."""

    def setUp(self):
        _app()
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.view = RgbMatrixView()
        self.view._add()
        self.table = {7: _panel_channels(48)}
        self.fixtures = [_fx(7, "LED-Balken")]
        self._orig_get_state = A.get_state
        A.get_state = lambda: NS(get_patched_fixtures=lambda: self.fixtures)

    def tearDown(self):
        A.get_state = self._orig_get_state
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)
        self.view.deleteLater()

    def _accept_panel_dialog(self, spalten=12, accept=True):
        """``PanelGridDialog.exec`` ersetzen: Spalten setzen und (nicht) bestaetigen.

        Ein modaler ``exec()`` blockiert headless; die Bedienung passiert hier
        also im Ersatz — am ECHTEN Dialogobjekt, nicht an einer Attrappe.
        """
        import src.ui.views.matrix_pattern_dialogs as M
        orig = M.PanelGridDialog.exec

        def fake(dlg):
            dlg._cols_spin.setValue(spalten)
            return (QDialog.DialogCode.Accepted if accept
                    else QDialog.DialogCode.Rejected)

        M.PanelGridDialog.exec = fake
        self.addCleanup(lambda: setattr(M.PanelGridDialog, "exec", orig))

    def test_knopf_raster_aus_geraet_setzt_das_grid(self):
        self._accept_panel_dialog(12)
        with _ChannelPatch(self.table):
            self.view._btn_panel_grid.click()
        m = self.view._current
        self.assertEqual((m.cols, m.rows), (12, 4))
        self.assertEqual(m.head_grid, list(range(48)))
        self.assertEqual(set(m.fixture_grid), {7})
        # Die gespeicherte Instanz muss mitziehen: eine Grid-Zuweisung ist live.
        self.assertEqual(self.view._saved.head_grid, list(range(48)))
        self.assertEqual(self.view._cols_spin.value(), 12)
        self.assertEqual(self.view._rows_spin.value(), 4)
        self.assertIn("LED-Balken", self.view._grid_label.text())

    def test_abbrechen_laesst_das_grid_unveraendert(self):
        vorher = list(self.view._current.fixture_grid)
        self._accept_panel_dialog(12, accept=False)
        with _ChannelPatch(self.table):
            self.view._btn_panel_grid.click()
        self.assertEqual(self.view._current.fixture_grid, vorher)

    def test_ohne_mehrzonen_geraet_erklaert_der_knopf_warum(self):
        self.fixtures = [_fx(9, "Einzel-PAR")]
        with _ChannelPatch({9: _panel_channels(1)}):
            self.view._btn_panel_grid.click()
        self.assertIn("mehreren Zonen", self.view._grid_label.text())

    def test_muster_assistent_legt_szenen_und_chaser_an(self):
        self._accept_panel_dialog(12)
        with _ChannelPatch(self.table):
            self.view._btn_panel_grid.click()

        import src.ui.views.matrix_pattern_dialogs as M
        orig = M.PatternWizardDialog.exec

        def fake(dlg):
            dlg._name_edit.setText("Bars nacheinander")
            dlg._dir_combo.setCurrentIndex(0)
            dlg._tempo_spin.setValue(8.0)
            return QDialog.DialogCode.Accepted

        M.PatternWizardDialog.exec = fake
        self.addCleanup(lambda: setattr(M.PatternWizardDialog, "exec", orig))

        from src.core.engine.function import FunctionType
        with _ChannelPatch(self.table):
            self.view._btn_pattern.click()

        chaser = [f for f in self.fm.all()
                  if f.function_type == FunctionType.Chaser
                  and f.name == "Bars nacheinander"]
        self.assertEqual(len(chaser), 1)
        self.assertEqual(len(chaser[0].steps), 12)
        self.assertAlmostEqual(chaser[0].steps[0].hold, 0.125)
        szenen = {f.id for f in self.fm.all()
                  if f.function_type == FunctionType.Scene}
        self.assertTrue({st.function_id for st in chaser[0].steps} <= szenen)
        self.assertIn("Bars nacheinander", self.view._grid_label.text())

    def test_muster_assistent_ohne_raster_erklaert_warum(self):
        self.view._current.fixture_grid = []
        self.view._btn_pattern.click()
        self.assertIn("Raster", self.view._grid_label.text())

    def test_im_folgemodus_ist_das_handraster_ausgeblendet(self):
        """Im Programmer folgt das Grid der Gruppe — ein Knopf, dessen Wirkung
        der naechste Auswahlwechsel wegwischt, waere schlimmer als keiner.
        Der Muster-Assistent LIEST nur und bleibt deshalb sichtbar."""
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        folgend = RgbMatrixView(follow_selection=True)
        self.addCleanup(folgend.deleteLater)
        self.assertFalse(folgend._btn_panel_grid.isVisible())
        self.assertFalse(folgend._btn_panel_grid.isVisibleTo(folgend))
        self.assertTrue(folgend._btn_pattern.isVisibleTo(folgend))


if __name__ == "__main__":
    unittest.main()
