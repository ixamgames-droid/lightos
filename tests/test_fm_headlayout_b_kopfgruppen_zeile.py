"""FM-HEADLAYOUT-B — der Ausweg aus der Falle „Kopf-Gruppe geloescht" war
ausgerechnet fuer Mehrkopf-Geraete unsichtbar.

Die Zeile „Kopf-Matrix-Gruppe: [Status] [Wiederherstellen]" stand im
Patch-Dialog INNERHALB des ``fixture_type == "matrix"``-Zweigs — ein Block eine
Ebene zu tief, dieselbe Klasse wie PIXELORDER-CRASH. Folge, gemessen an einem
Spider: Er bekommt die Mehrkopf-Combo („Mehrkopf-Programmierung"), hat eine
Pro-Kopf-Matrix-Gruppe und kann sie genauso verlieren — nur den Knopf, der sie
zurueckholt, sah er nie. Genau die Geraete, fuer die FM-HEADLAYOUT die Falle
schliessen wollte, sahen den Ausweg nicht.

★ Was diese Datei misst, misst sie am ECHTEN Dialog und an der ECHTEN Wirkung:

* Der Dialog wird GEZEIGT (``show()``) und danach nur ausgewertet, was Qt als
  sichtbar fuehrt. Ein ``setVisible(False)`` im Produktionscode faellt damit
  auf; „Widget existiert" wuerde es nicht.
* Beschriftung, Status und Knopf werden als EINE Formularzeile nachgewiesen
  (``QFormLayout``-Zeilenindex), nicht als drei irgendwo verstreute Widgets.
* Der Knopf wird GEKLICKT (``QPushButton.click()`` → das echte Signal → der
  echte Slot ``_restore_head_group``), nachdem die Gruppe ueber den ECHTEN
  Loeschweg der Oberflaeche (``FixtureGroupView._delete_group``) verschwunden
  ist. Gemessen wird danach die Gruppe in der Show-DB, nicht ein Rueckgabewert.

Geraetearten (beide gefordert, beide hier):

* **Spider** — ``SPIDER14`` (U King, ``fixture_type`` „moving_head", 2 faerbbare
  Baenke) und ``MOVBAR4`` (4 Koepfe, die 4-Kopf-Lage aus dem Befund). Das war
  der blinde Fleck.
* **Matrix-Panel** — ``ZQ06121`` mit 48 Zonen. Regressionswache: beim
  Ausruecken darf die Zeile dort nicht verloren gehen.

POSITIVKONTROLLE (die neue Grenze ``_heads >= 2`` darf im Normalfall NICHT
anschlagen und auch nicht ueberall anschlagen):

* Ein PAR (1 Kopf, kein Matrix-Typ) bekommt die Zeile nicht.
* Ein Panel vom Typ „matrix" mit nur EINEM faerbbaren Kopf (ADJ Dotz,
  Gesamtmodus) bekommt sie ebenfalls nicht — die schaerfere Gegenprobe, denn
  dieses Geraet faellt nicht schon durch seinen Typ heraus. Dass dort wirklich
  nichts zurueckzuholen waere, wird nachgemessen: ``create_head_matrix_group``
  legt fuer dieses Geraet keine Gruppe an.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QFormLayout, QLabel,   # noqa: E402
                               QPushButton, QWidget)
from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

import pytest as _pytest_fmhb                                        # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@_pytest_fmhb.fixture(autouse=True)
def _fmhb_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


# Die Beschriftung der Zeile und die Aufschrift des Knopfs — genau das, was der
# Benutzer sucht, wenn er „meine Kopf-Gruppe ist weg" behebt.
BESCHRIFTUNG = "Kopf-Matrix-Gruppe:"
KNOPF = "Wiederherstellen"

# Matrix-Panel mit vielen einzeln faerbbaren Zonen (Davids Balken).
MODUS_PANEL = "154-Kanal 48 Zonen RGB + 8x Weiss"
KANAELE_PANEL = 154

# Typ „matrix", aber nur EIN faerbbarer Kopf: Panel-Gesamtmodus der ADJ Dotz.
MODUS_EINKOPF = "3-Kanal RGB"
KANAELE_EINKOPF = 3


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _StummeFrage:
    """Ersatz fuer ``QMessageBox`` im Loesch-Weg — der modale Ruecktfrage-Dialog
    blockiert headless bis zum Timeout. Es wird „Ja" geantwortet, also genau
    das, was der Benutzer tut, der die Gruppe (versehentlich) loescht. Keine
    Attrappe im gemessenen Pfad: geloescht wird von ``_delete_group`` selbst,
    gemessen wird die Show-DB."""

    class StandardButton:
        Yes = 1
        No = 0

    @staticmethod
    def question(*_a, **_kw):
        return 1

    @staticmethod
    def warning(*_a, **_kw):
        return 0

    @staticmethod
    def information(*_a, **_kw):
        return 0


class _Basis(unittest.TestCase):
    def setUp(self):
        from src.core.app_state import get_state
        from src.core.database.fixture_db import (engine as fdb_engine,
                                                  ensure_builtins)
        from src.core.database.models import FixtureProfile
        from src.core.show.show_file import reset_show
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        with Session(fdb_engine()) as s:
            def _pid(short):
                return int(s.execute(select(FixtureProfile.id).where(
                    FixtureProfile.short_name == short)).scalar_one())
            self.pid_spider = _pid("SPIDER14")
            self.pid_movbar = _pid("MOVBAR4")
            self.pid_panel = _pid("ZQ06121")
            self.pid_dotz = _pid("DOTZMATRIX")
            self.pid_par = _pid("ZQ01424")

    # ── Geraete patchen (wie die Oberflaeche: ohne Sonderwuensche) ──────────
    def _add(self, fid, **kw):
        from src.core.database.models import PatchedFixture
        self.state.add_fixture(PatchedFixture(fid=fid, universe=1, **kw),
                               undoable=False)
        return self._frisch(fid)

    def _spider(self, fid=1):
        """U King Spider 14ch — ``fixture_type`` „moving_head", zwei faerbbare
        Baenke (Bar L / Bar R). Das Geraet aus dem Befund."""
        return self._add(fid, label="Spider", fixture_profile_id=self.pid_spider,
                         mode_name="14-Kanal", address=1, channel_count=14,
                         manufacturer_name="U King", fixture_name="Spider 14ch",
                         fixture_type="moving_head")

    def _vierkopf(self, fid=2):
        """Vier einzeln faerbbare Koepfe, kein Matrix-Typ — die 4-Kopf-Lage aus
        dem Befund („gemessen an einem 4-Kopf-Spider")."""
        return self._add(fid, label="Bar 4x", fixture_profile_id=self.pid_movbar,
                         mode_name="22-Kanal 4×Move RGB", address=100,
                         channel_count=22, manufacturer_name="Generic",
                         fixture_name="LED Moving Bar 4×",
                         fixture_type="moving_head")

    def _panel(self, fid=3):
        return self._add(fid, label="Balken", fixture_profile_id=self.pid_panel,
                         mode_name=MODUS_PANEL, address=200,
                         channel_count=KANAELE_PANEL, manufacturer_name="U King",
                         fixture_name="ZQ06121 LED-Balken 768 (stage light)",
                         fixture_type="matrix")

    def _einkopf_matrix(self, fid=4):
        return self._add(fid, label="Dotz gesamt",
                         fixture_profile_id=self.pid_dotz,
                         mode_name=MODUS_EINKOPF, address=400,
                         channel_count=KANAELE_EINKOPF, manufacturer_name="ADJ",
                         fixture_name="Dotz Matrix", fixture_type="matrix")

    def _par(self, fid=5):
        return self._add(fid, label="PAR links", fixture_profile_id=self.pid_par,
                         mode_name="8-Kanal RGBW", address=450, channel_count=8,
                         manufacturer_name="Generic",
                         fixture_name="Stage Light ZQ01424", fixture_type="par")

    def _frisch(self, fid):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _kopfzahl(self, fx) -> int:
        from src.core.app_state import color_head_count
        return int(color_head_count(fx))

    # ── Der echte Dialog und was der Benutzer davon SIEHT ───────────────────
    def _dialog(self, fx):
        from src.ui.views.patch_view import PatchFixtureEditDialog
        dlg = PatchFixtureEditDialog(self.state, fx)
        self.addCleanup(dlg.deleteLater)
        dlg.show()          # Sichtbarkeit wird gemessen, nicht angenommen
        return dlg

    def _zeile(self, dlg):
        """Die Formularzeile ``BESCHRIFTUNG`` als ``(Beschriftung, Feld)`` —
        oder ``None``, wenn es sie nicht gibt.

        Ueber den ``QFormLayout``-Zeilenindex, damit „die Zeile" auch wirklich
        eine ist: Beschriftung links, Status + Knopf im selben Feld rechts. Drei
        Widgets irgendwo im Dialog wuerden diese Pruefung nicht bestehen."""
        for form in dlg.findChildren(QFormLayout):
            for i in range(form.rowCount()):
                links = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
                rechts = form.itemAt(i, QFormLayout.ItemRole.FieldRole)
                if links is None or rechts is None:
                    continue
                wl, wr = links.widget(), rechts.widget()
                if isinstance(wl, QLabel) and wl.text() == BESCHRIFTUNG:
                    return wl, wr
        return None

    def _sichtbare_zeile(self, dlg):
        """``(Status-Label, Knopf)`` der sichtbaren Zeile — scheitert laut,
        wenn die Zeile fehlt oder unsichtbar ist."""
        zeile = self._zeile(dlg)
        self.assertIsNotNone(
            zeile, f"keine Formularzeile {BESCHRIFTUNG!r} im Dialog — "
                   f"vorhandene Beschriftungen: {self._beschriftungen(dlg)}")
        beschriftung, feld = zeile
        self.assertTrue(beschriftung.isVisible(),
                        f"die Zeile {BESCHRIFTUNG!r} ist da, aber unsichtbar")
        self.assertIsInstance(feld, QWidget)
        self.assertTrue(feld.isVisible(), "das Feld der Zeile ist unsichtbar")
        knoepfe = [w for w in feld.findChildren(QPushButton)
                   if w.isVisible() and w.text() == KNOPF]
        self.assertEqual(len(knoepfe), 1,
                         f"genau ein sichtbarer Knopf {KNOPF!r} erwartet, "
                         f"gefunden: {[w.text() for w in feld.findChildren(QPushButton)]}")
        stati = [w for w in feld.findChildren(QLabel)
                 if w.isVisible() and w.text().strip()]
        self.assertEqual(len(stati), 1,
                         f"genau eine Status-Anzeige erwartet, gefunden: "
                         f"{[w.text() for w in feld.findChildren(QLabel)]}")
        return stati[0], knoepfe[0]

    def _beschriftungen(self, dlg) -> list[str]:
        out = []
        for form in dlg.findChildren(QFormLayout):
            for i in range(form.rowCount()):
                it = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
                w = it.widget() if it is not None else None
                if isinstance(w, QLabel):
                    out.append(w.text())
        return out

    # ── Die Gruppe ueber den ECHTEN Weg der Oberflaeche loeschen ────────────
    def _gruppe_im_editor_loeschen(self, gid: int) -> None:
        """So, wie sie in Wirklichkeit verschwindet: im Gruppen-Editor
        ausgewaehlt und geloescht. Kein direktes DELETE im Test — der Weg, der
        die Falle aufstellt, soll auch der gemessene sein."""
        from src.ui.views import fixture_group_view as fgv
        view = fgv.FixtureGroupView()
        self.addCleanup(view.deleteLater)
        view._reload_group_list(select_gid=gid)
        self.assertIsNotNone(view._current_group, "keine Gruppe im Editor")
        self.assertEqual(view._current_group.id, gid,
                         "der Editor hat eine andere Gruppe ausgewaehlt")
        echt = fgv.QMessageBox
        fgv.QMessageBox = _StummeFrage
        try:
            view._delete_group()
        finally:
            fgv.QMessageBox = echt


class ZeileErscheintFuerJedesMehrkopfGeraetTest(_Basis):
    """★ Der Kern des Befunds: die Zeile haengt an der KOPFZAHL, nicht am
    Geraetetyp. Eine Mutation, die den Block wieder eine Ebene tiefer (in den
    ``fixture_type == "matrix"``-Zweig) legt, macht die beiden Spider-Tests
    rot und laest den Matrix-Test gruen — genau der Zustand vor dem Fix."""

    def test_spider_zeigt_die_zeile(self):
        fx = self._spider()
        self.assertGreaterEqual(
            self._kopfzahl(fx), 2,
            "dieser Spider hat keine zwei faerbbaren Koepfe — dann ist er die "
            "falsche Messprobe")
        self.assertNotEqual(
            fx.fixture_type, "matrix",
            "der Spider gilt als Matrix-Geraet — dann misst dieser Test den "
            "Befund nicht mehr (er lebte genau von dieser Unterscheidung)")
        self._sichtbare_zeile(self._dialog(fx))

    def test_vierkopf_geraet_zeigt_die_zeile(self):
        """Die Lage aus dem Befund: vier Koepfe, kein Matrix-Typ."""
        fx = self._vierkopf()
        self.assertEqual(self._kopfzahl(fx), 4)
        self.assertNotEqual(fx.fixture_type, "matrix")
        self._sichtbare_zeile(self._dialog(fx))

    def test_matrix_panel_zeigt_die_zeile_weiterhin(self):
        """Regressionswache: beim Ausruecken darf das Panel die Zeile nicht
        verlieren — dort war sie ja schon."""
        fx = self._panel()
        self.assertEqual(fx.fixture_type, "matrix")
        self.assertGreaterEqual(self._kopfzahl(fx), 2)
        self._sichtbare_zeile(self._dialog(fx))

    def test_spider_hat_die_mehrkopf_combo_und_die_zeile_zusammen(self):
        """Der Widerspruch, der den Befund ausmachte: dasselbe Geraet bekam die
        Mehrkopf-Programmierung angeboten (also „du hast eine Kopf-Matrix"),
        aber nicht den Weg zurueck. Beide Felder haengen jetzt an derselben
        Bedingung — hier wird gemessen, dass sie gemeinsam auftreten."""
        dlg = self._dialog(self._spider())
        self.assertIsNotNone(dlg._combo_head_mode,
                             "kein Mehrkopf-Feld — dann misst dieser Test den "
                             "Widerspruch nicht")
        self._sichtbare_zeile(dlg)


class KnopfHoltDieGeloeschteGruppeZurueckTest(_Basis):
    """★ Sichtbar allein genuegt nicht — der Knopf muss am Spider auch WIRKEN.
    Gemessen wird die Kette: patchen → Auto-Gruppe da → im Gruppen-Editor
    geloescht → Status „fehlt" → Klick → Gruppe wieder da, Status „vorhanden".
    Nichts davon wird nachgerechnet; die Gruppe kommt jedes Mal frisch aus der
    Show-DB (``find_head_matrix_group``)."""

    def _durchspielen(self, fx):
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        self.assertIsNotNone(
            gid, "beim Patchen entstand keine Kopf-Gruppe — dann gaebe es "
                 "nichts zu verlieren und der Knopf waere sinnlos")

        self._gruppe_im_editor_loeschen(gid)
        self.assertIsNone(
            self.state.find_head_matrix_group(fx.fid),
            "die Gruppe ueberlebte das Loeschen im Editor — dann stellt dieser "
            "Test die Falle gar nicht")

        status, knopf = self._sichtbare_zeile(self._dialog(self._frisch(fx.fid)))
        self.assertEqual(status.text(), "fehlt",
                         "der Status meldet nicht „fehlt“, obwohl die Gruppe "
                         "geloescht ist")
        knopf.click()          # echtes Signal -> echter Slot
        self.assertIsNotNone(
            self.state.find_head_matrix_group(fx.fid, dedicated=True),
            "der Klick hat die Kopf-Gruppe nicht wiederhergestellt")
        self.assertEqual(status.text(), "vorhanden",
                         "der Status blieb nach dem Wiederherstellen stehen")

    def test_spider_kopfgruppe_ist_wieder_herstellbar(self):
        self._durchspielen(self._spider())

    def test_vierkopf_kopfgruppe_ist_wieder_herstellbar(self):
        self._durchspielen(self._vierkopf())

    def test_zweiter_klick_legt_kein_duplikat_an(self):
        """Der Knopf verspricht Idempotenz — das wird gemessen, nicht geglaubt.
        (Ohne diese Messung koennte „wirkt" auch heissen: legt jedes Mal eine
        weitere Gruppe an.)"""
        from src.core.database.models import FixtureGroup
        fx = self._spider()
        gid = self.state.find_head_matrix_group(fx.fid, dedicated=True)
        self._gruppe_im_editor_loeschen(gid)
        _status, knopf = self._sichtbare_zeile(self._dialog(self._frisch(fx.fid)))
        knopf.click()
        knopf.click()
        with self.state._session() as s:
            gruppen = [g for g in s.execute(select(FixtureGroup)).scalars()
                       if (g.folder or "") == "Multi-Head"]
        self.assertEqual(len(gruppen), 1,
                         f"zwei Klicks ergaben {len(gruppen)} Kopf-Gruppen: "
                         f"{[g.name for g in gruppen]}")


class EinKopfGeraeteBekommenDieZeileNichtTest(_Basis):
    """POSITIVKONTROLLE zur neuen Grenze ``_heads >= 2``: sie darf nicht
    ueberall anschlagen. Wo ``create_head_matrix_group`` gar keine Gruppe
    anlegt, waere „fehlt" eine Behauptung ueber etwas, das dieses Geraet nicht
    haben kann, und „Wiederherstellen" ein stiller No-Op.

    Ohne diese Klasse wuerde auch ein Fix durchgehen, der die Bedingung ganz
    weglaesst — die Zeile stuende dann bei jedem PAR."""

    def test_par_bekommt_die_zeile_nicht(self):
        fx = self._par()
        self.assertEqual(self._kopfzahl(fx), 1)
        self.assertIsNone(self._zeile(self._dialog(fx)),
                          "ein einkoepfiger PAR zeigt die Kopf-Matrix-Zeile")

    def test_einkopf_matrix_bekommt_die_zeile_nicht(self):
        """★ Die schaerfere Gegenprobe: ``fixture_type`` ist „matrix" — dieses
        Geraet faellt also NICHT schon durch seinen Typ heraus, sondern nur
        durch die Kopfzahl. Dass es wirklich nichts zurueckzuholen gibt, wird
        an der Produktionsfunktion nachgemessen."""
        fx = self._einkopf_matrix()
        self.assertEqual(self._kopfzahl(fx), 1,
                         "dieses Geraet hat mehrere Koepfe — falsche Gegenprobe")
        self.assertEqual(fx.fixture_type, "matrix",
                         "ohne Matrix-Typ waere die Gegenprobe stumpf")
        self.assertIsNone(
            self.state.create_head_matrix_group(fx),
            "fuer dieses Geraet entsteht doch eine Kopf-Gruppe — dann muesste "
            "die Zeile erscheinen und diese Gegenprobe weg")
        dlg = self._dialog(fx)
        self.assertIsNotNone(
            dlg._combo_pixel_order,
            "ohne Pixel-Reihenfolge-Feld faellt dieses Geraet schon wie der "
            "PAR heraus — dann misst die Gegenprobe die Kopfzahl nicht")
        self.assertIsNone(self._zeile(dlg),
                          "ein Panel mit nur EINEM faerbbaren Kopf zeigt die "
                          "Kopf-Matrix-Zeile")


if __name__ == "__main__":
    unittest.main()
