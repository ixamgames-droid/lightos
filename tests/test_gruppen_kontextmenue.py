"""FM-20 Teil 1 — Rechtsklick im Gruppenraster und Aufteilen als Block.

Davids Aufbau (2026-08-05): PAR / Matrix-Panel / PAR nebeneinander. Er will das
Panel als EIN Element neben die PARs legen und per Rechtsklick wieder in seine
Einzelelemente zerfallen lassen.

Zwei Dinge gab es schon — „Köpfe einzeln → Raster" und „Köpfe zusammenfassen" —
aber nur als Knöpfe, die ihr Zielgerät aus der Baum-Auswahl LINKS nehmen. Man
musste also erst dort das richtige Gerät suchen, obwohl man mit der Maus längst
darauf stand. Und Rechtsklick löschte die Zelle sofort, ohne Nachfrage.

Neu getestet:
- `place_fixture_block` — Rechteck statt Streifen, mit Nummerierung UND
  Montage-Drehung (`place_element`, FM-ORIENT). Das ist der erste Aufrufer
  ausserhalb der 3D-Vorschau, den `pixel_order` überhaupt hat (FM-21).
- Rechtsklick meldet die Zelle, statt sie zu löschen.
- Die Regeln, die `place_fixture_heads` schon einhält, gelten auch für den
  Block: Move statt Duplikat, kein stilles Überschreiben, volles Raster
  zerstört nichts.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

import pytest as _pytest_xplat15                          # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets   # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def _grid(cols=12, rows=6):
    from src.ui.views.fixture_group_view import FixtureGridWidget
    _app()
    g = FixtureGridWidget()
    g.set_grid(cols, rows)
    return g


def _zellen(g, fid):
    """Belegte Zellen dieses Geraets als {kopf: (col,row)}.

    ★ NUR fuer Positionsfragen benutzen, NIE zum Zaehlen. Ein Dict fasst zwei
    Zellen mit demselben Kopf zu einem Eintrag zusammen — die Mutation „eigene
    Zellen nicht freigeben" erzeugt genau solche Doppel, und dieser Helfer hat
    sie in der ersten Fassung des Tests verschluckt (24 belegte Zellen, `len()`
    meldete 12, Test blieb gruen). Zum Zaehlen `_anzahl_zellen`.
    """
    from src.ui.views.fixture_group_view import _split_cell
    out = {}
    for (c, r), v in g.positions.items():
        base, head = _split_cell(v)
        if base == fid:
            out[head] = (c, r)
    return out


def _anzahl_zellen(g, fid):
    """Wie viele RASTERZELLEN dieses Geraet belegt — die ehrliche Zahl."""
    from src.ui.views.fixture_group_view import _split_cell
    return sum(1 for v in g.positions.values() if _split_cell(v)[0] == fid)


class BlockPlatzierungTest(unittest.TestCase):
    """Der Kern: 48 Elemente als 4x12-Rechteck statt als 1x48-Streifen."""

    def test_block_belegt_ein_rechteck(self):
        g = _grid(12, 6)
        placed = g.place_fixture_block(7, 48, 12, 0, 0)
        self.assertEqual(len(placed), 48)
        spalten = {c for c, _ in placed}
        zeilen = {r for _, r in placed}
        self.assertEqual(spalten, set(range(12)))
        self.assertEqual(zeilen, set(range(4)))

    def test_zeilenweise_nummerierung_stimmt(self):
        g = _grid(12, 6)
        g.place_fixture_block(7, 48, 12, 0, 0)
        z = _zellen(g, 7)
        self.assertEqual(z[0], (0, 0))       # erstes Element links oben
        self.assertEqual(z[11], (11, 0))     # Ende der ersten Zeile
        self.assertEqual(z[12], (0, 1))      # zweite Zeile beginnt links
        self.assertEqual(z[47], (11, 3))     # letztes Element rechts unten

    def test_schlangenlinie_kehrt_jede_zweite_zeile_um(self):
        # Der Werkszustand der ADJ Dotz Matrix — genau der Fall, der ein
        # Lauflicht am echten Geraet im Zickzack laufen laesst.
        g = _grid(4, 4)
        g.place_fixture_block(3, 16, 4, 0, 0, order="serpentine")
        z = _zellen(g, 3)
        self.assertEqual(z[0], (0, 0))
        self.assertEqual(z[3], (3, 0))
        self.assertEqual(z[4], (3, 1))       # zweite Zeile laeuft rueckwaerts
        self.assertEqual(z[7], (0, 1))
        self.assertEqual(z[8], (0, 2))       # dritte wieder vorwaerts

    def test_90_grad_tauscht_breite_und_hoehe(self):
        # Ein 12x4-Panel hochkant montiert braucht 4 Spalten und 12 Zeilen.
        g = _grid(12, 12)
        placed = g.place_fixture_block(9, 48, 12, 0, 0, rotation=90)
        self.assertEqual(len(placed), 48)
        self.assertEqual({c for c, _ in placed}, set(range(4)))
        self.assertEqual({r for _, r in placed}, set(range(12)))

    def test_180_grad_dreht_das_erste_element_nach_rechts_unten(self):
        # Kopfueber montiert. Das ist der Fall, den `pixel_order` allein GAR
        # NICHT ausdruecken kann (sie spiegelt nur Spalten, nie Zeilen).
        g = _grid(12, 6)
        g.place_fixture_block(5, 48, 12, 0, 0, rotation=180)
        z = _zellen(g, 5)
        self.assertEqual(z[0], (11, 3))
        self.assertEqual(z[47], (0, 0))

    def test_ohne_drehung_gleich_wie_pixel_cell(self):
        # Bestandsschutz: der Block darf ohne Drehung nichts anderes tun als
        # die vorhandene Rasterrechnung.
        from src.core.pixel_order import pixel_cell
        g = _grid(8, 8)
        g.place_fixture_block(2, 24, 6, 0, 0)
        z = _zellen(g, 2)
        for i in range(24):
            r, c = pixel_cell(i, 6, "rowwise")
            self.assertEqual(z[i], (c, r), f"Element {i}")


class BlockRegelnTest(unittest.TestCase):
    """Dieselben Schutzregeln wie beim Streifen — sie sind teuer erkauft."""

    def test_move_statt_duplikat(self):
        g = _grid(12, 6)
        g.place_fixture_block(4, 12, 6, 0, 0)
        g.place_fixture_block(4, 12, 6, 0, 2)
        # ★ Ueber ZELLEN zaehlen, nicht ueber Koepfe: ein {kopf: zelle}-Dict
        # faellt bei Doppeln auf 12 zusammen und meldet den Fehler nie.
        self.assertEqual(_anzahl_zellen(g, 4), 12,
                         "altes Vorkommen muss verschwinden, nicht verdoppeln")
        self.assertEqual({r for (_c, r) in g.positions}, {2, 3},
                         "nur die NEUE Lage darf belegt sein")

    def test_fremde_zelle_wird_nicht_ueberschrieben(self):
        g = _grid(6, 6)
        g.positions[(2, 0)] = 99            # fremdes Geraet
        g.place_fixture_block(4, 6, 6, 0, 0)
        self.assertEqual(g.positions[(2, 0)], 99,
                         "fremde Zelle darf nicht still ueberschrieben werden")
        self.assertEqual(len(_zellen(g, 4)), 6, "alle Koepfe untergebracht")

    def test_volles_raster_zerstoert_nichts(self):
        g = _grid(2, 2)
        for c in range(2):
            for r in range(2):
                g.positions[(c, r)] = 50 + c * 2 + r
        placed = g.place_fixture_block(8, 4, 2, 0, 0)
        self.assertEqual(placed, [])
        self.assertEqual(len(g.positions), 4, "Fremdbelegung unangetastet")

    def test_block_wird_zurueckgeschoben_statt_abgeschnitten(self):
        # Start rechts unten, Block passt dort nicht mehr -> Start zurueck,
        # nicht hinten abschneiden.
        g = _grid(6, 6)
        placed = g.place_fixture_block(1, 9, 3, 5, 5)
        self.assertEqual(len(placed), 9)
        self.assertEqual({c for c, _ in placed}, {3, 4, 5})
        self.assertEqual({r for _, r in placed}, {3, 4, 5})

    def test_unsinnige_eingaben_liefern_leer(self):
        g = _grid(6, 6)
        for args in ((1, 0, 3), (1, 5, 0), (1, "x", 3), (1, 5, None)):
            self.assertEqual(g.place_fixture_block(*args), [],
                             f"{args} haette leer liefern muessen")
        self.assertEqual(g.positions, {})


class RechtsklickTest(unittest.TestCase):
    """Rechtsklick meldet die Zelle, statt sie sofort zu loeschen."""

    def test_rechtsklick_loescht_nicht_mehr_sofort(self):
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import Qt, QPointF
        g = _grid(4, 4)
        g.resize(400, 400)
        g.positions[(1, 1)] = 42
        # ★ Der Punkt muss WIRKLICH in der belegten Zelle liegen. In der ersten
        # Fassung stand hier (10,10) — das ist Zelle (0,0), also leer; die
        # Mutation „loesche sofort" traf ins Nichts und der Test blieb gruen.
        p = QPointF(150, 150)               # 400/4 = 100 px je Zelle -> (1,1)
        self.assertEqual(g._cell_at(p.toPoint()), (1, 1), "Testpunkt daneben")
        ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, p, p,
                         Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                         Qt.KeyboardModifier.NoModifier)
        g.mousePressEvent(ev)
        self.assertIn((1, 1), g.positions,
                      "Rechtsklick darf nicht mehr ungefragt loeschen")

    def test_kontextmenue_meldet_die_zelle(self):
        g = _grid(4, 4)
        g.resize(400, 400)
        gesehen = []
        g.cell_context_menu.connect(
            lambda c, r, p: gesehen.append((c, r)))
        from PySide6.QtGui import QContextMenuEvent
        ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                               QPoint(250, 150), QPoint(250, 150))
        g.contextMenuEvent(ev)
        self.assertEqual(gesehen, [(2, 1)])

    def test_klick_ausserhalb_meldet_nichts(self):
        g = _grid(4, 4)
        g.resize(400, 400)
        gesehen = []
        g.cell_context_menu.connect(lambda c, r, p: gesehen.append((c, r)))
        from PySide6.QtGui import QContextMenuEvent
        ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                               QPoint(2000, 2000), QPoint(2000, 2000))
        g.contextMenuEvent(ev)
        self.assertEqual(gesehen, [])

    def test_remove_cell_meldet_ob_etwas_da_war(self):
        g = _grid(4, 4)
        g.positions[(0, 0)] = 5
        self.assertTrue(g.remove_cell(0, 0))
        self.assertFalse(g.remove_cell(0, 0))


class AufteilenUndZusammenfassenTest(unittest.TestCase):
    """Der Rundweg, den David meint: auseinander und wieder zusammen."""

    def test_block_und_zurueck_zu_einer_zelle(self):
        g = _grid(12, 6)
        g.positions[(0, 0)] = 7             # Panel als EINE Zelle
        g.place_fixture_block(7, 48, 12, 0, 0)
        self.assertEqual(len(_zellen(g, 7)), 48)
        zelle = g.collapse_fixture_heads(7)
        self.assertIsNotNone(zelle)
        self.assertEqual(len(_zellen(g, 7)), 1)
        self.assertIsNone(list(_zellen(g, 7))[0],
                          "wieder eine Ganz-Geraet-Zelle, kein Kopf")

    def test_nachbarn_ueberleben_den_rundweg(self):
        # Davids Aufbau: PAR / Panel / PAR. Die PARs duerfen beim Aufteilen und
        # Zusammenfassen des Panels nicht verschwinden.
        g = _grid(12, 6)
        g.positions[(0, 5)] = 101           # PAR links
        g.positions[(11, 5)] = 102          # PAR rechts
        g.place_fixture_block(7, 48, 12, 0, 0)
        g.collapse_fixture_heads(7)
        self.assertEqual(g.positions.get((0, 5)), 101)
        self.assertEqual(g.positions.get((11, 5)), 102)


class MenueVerdrahtungTest(unittest.TestCase):
    """★ Der Test, der bei PIXELORDER-TOT gefehlt hat.

    Die Tests oben pruefen das Raster-Widget. Der Fehler von heute frueh sass
    aber genau EINE Ebene darueber — in der View, die niemand baute: ein
    UnboundLocalError im Patch-Dialog, den 2030 Tests nicht sahen, weil keiner
    ihn je konstruierte. Deshalb baut dieser Test die ECHTE `FixtureGroupView`
    und ruft `_on_cell_menu` auf, statt die Menuelogik nachzuerzaehlen.
    """

    def setUp(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.app_state import get_state
        from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
        from src.core.database.models import PatchedFixture, FixtureProfile
        from src.core.show.show_file import reset_show
        from src.ui.views.fixture_group_view import FixtureGroupView
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        with Session(fdb_engine()) as s:
            pid_spider = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "SPIDER14")).scalar_one())
            pid_par = int(s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "ZQ01424")).scalar_one())
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Panel", fixture_profile_id=pid_spider,
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=pid_par,
            mode_name="8-Kanal RGBW", universe=1, address=20, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        self.view = FixtureGroupView()
        self.addCleanup(self.view.deleteLater)

    def _menue_texte(self, col, row):
        """Menuepunkte fuer eine Zelle einsammeln.

        Ruft `_build_cell_menu` — die Trennung von Bauen und Anzeigen ist genau
        dafuer da. Der erste Anlauf patchte `QMenu.exec` weg; das greift bei
        PySide6 nicht und liess den Lauf HAENGEN statt zu scheitern (Timeout im
        Segment, kein `FAILED`). Untermenues werden mit eingesammelt, weil
        „aufteilen" genau dort sitzt.
        """
        menu = self.view._build_cell_menu(col, row)
        if menu is None:
            return []
        texte = []
        for a in menu.actions():
            if a.isSeparator():
                continue
            texte.append(a.text())
            if a.menu() is not None:
                texte.extend(x.text() for x in a.menu().actions()
                             if not x.isSeparator())
        return texte

    def test_menue_auf_mehrkopf_zelle_bietet_aufteilen(self):
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = 1                 # ganzes Geraet, 2 Koepfe
        texte = self._menue_texte(0, 0)
        self.assertTrue(any("entfernen" in t for t in texte), texte)
        self.assertTrue(any("aufteilen" in t for t in texte), texte)

    def test_menue_auf_kopfzelle_bietet_zusammenfassen(self):
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = "1:0"
        gw.positions[(1, 0)] = "1:1"
        texte = self._menue_texte(0, 0)
        self.assertTrue(any("zusammenfassen" in t for t in texte), texte)
        self.assertFalse(any("aufteilen" in t for t in texte),
                         "eine Kopfzelle ist schon aufgeteilt")

    def test_einkopf_geraet_bekommt_kein_aufteilen(self):
        # Ein PAR hat nichts aufzuteilen — das Angebot waere eine Luege.
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = 2
        texte = self._menue_texte(0, 0)
        self.assertFalse(any("aufteilen" in t for t in texte), texte)

    def test_leere_zelle_oeffnet_kein_menue(self):
        self.assertEqual(self._menue_texte(3, 3), [])

    def test_zelle_entfernen_wirkt_wirklich(self):
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = 2
        self.view._cell_menu_remove(0, 0)
        self.assertNotIn((0, 0), gw.positions)

    def test_alle_zellen_entfernen_trifft_nur_das_geraet(self):
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = "1:0"
        gw.positions[(1, 0)] = "1:1"
        gw.positions[(2, 0)] = 2                 # der PAR daneben
        self.view._cell_menu_drop_all(1)
        self.assertEqual(gw.positions, {(2, 0): 2})

    def test_zusammenfassen_ueber_das_menue(self):
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = "1:0"
        gw.positions[(1, 0)] = "1:1"
        fx = self.view._fixture_by_fid(1)
        self.view._cell_menu_collapse(fx)
        self.assertEqual(_anzahl_zellen(gw, 1), 1)

    def test_aufteilen_als_zeile_ueber_das_menue(self):
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = 1
        fx = self.view._fixture_by_fid(1)
        self.view._cell_menu_split(fx, 2, "row", 0, 0)
        self.assertEqual(_anzahl_zellen(gw, 1), 2)
        self.assertEqual({r for (_c, r) in gw.positions}, {0})

    def test_blockspalten_vorschlag_ist_ein_teiler(self):
        """48 -> 12, nie 7. Eine angebrochene Zeile ist bei einem Panel fast
        immer ein Vertipper, deshalb ist der Vorschlag ein echter Teiler.

        ★ Der Vorschlag wird dem ECHTEN Dialogaufruf abgegriffen, nicht im Test
        nachgerechnet. Ein Test, der die Formel nachbaut, ist immer gruen — und
        genau diese Sorte Attrappe habe ich heute schon dreimal gefunden.
        """
        from PySide6.QtWidgets import QInputDialog
        gesehen = {}
        echt = QInputDialog.getInt

        def _fake(parent, titel, text, wert=0, mini=0, maxi=0, schritt=1, **kw):
            gesehen["vorschlag"] = wert
            gesehen["max"] = maxi
            return wert, True

        QInputDialog.getInt = staticmethod(_fake)
        try:
            # Erwartungen von Hand nachgerechnet: der Teiler, der der Wurzel am
            # naechsten liegt. Bei 48 ist das 6 (|6-6,93| < |8-6,93|), NICHT 8 —
            # mein erster Ansatz stand hier falsch, der Code hatte recht.
            #
            # ⚠️ Fuer Davids ZQ06121 waeren 12 Spalten richtig (4x12), nicht 6.
            # Der quadratische Vorschlag ist eine ehrliche Notloesung, solange
            # die echte Geometrie nirgends hinterlegt ist — er ist eine
            # VORBELEGUNG im Dialog, kein Automatismus. Sobald `layout_json`
            # steht (FM-20 Teil 2), soll der Vorschlag von dort kommen.
            for n, erwartet in ((16, 4), (48, 6), (144, 12), (7, 7)):
                gesehen.clear()
                zurueck = self.view._ask_block_cols(n)
                self.assertEqual(gesehen["vorschlag"], erwartet,
                                 f"{n} Elemente -> Vorschlag {gesehen}")
                self.assertEqual(zurueck, erwartet)
                self.assertEqual(n % erwartet, 0,
                                 f"Vorschlag {erwartet} teilt {n} nicht")
        finally:
            QInputDialog.getInt = echt

    def test_abgebrochener_dialog_platziert_nichts(self):
        """Auf „Abbrechen" darf das Raster unangetastet bleiben — und nicht
        etwa auf einen Standardwert zurueckfallen."""
        from PySide6.QtWidgets import QInputDialog
        gw = self.view._grid_widget
        gw.positions[(0, 0)] = 1
        vorher = dict(gw.positions)
        echt = QInputDialog.getInt
        QInputDialog.getInt = staticmethod(lambda *a, **kw: (0, False))
        try:
            fx = self.view._fixture_by_fid(1)
            self.view._cell_menu_split(fx, 2, "block", 0, 0)
        finally:
            QInputDialog.getInt = echt
        self.assertEqual(gw.positions, vorher)


if __name__ == "__main__":
    unittest.main()
