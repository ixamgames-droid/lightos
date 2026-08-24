"""FM-23 — der Fixture-Editor kann Panel-Geometrie hinterlegen (und behaelt sie).

**Der Befund.** ``FixtureMode.grid_rows``/``grid_cols`` (VIZ-50a) und
``white_rows``/``white_cols`` (CDX-52) wurden ausschliesslich von den
mitgelieferten Builtin-Daten und dem Nachtrag ``_ensure_panel_geometrie``
gesetzt. Ein selbstgebautes Panel hatte gar keinen Weg, seine Form zu
hinterlegen: der 3D-Renderer riet sie weiter near-square aus der Pixelzahl (aus
einem 4x12-Balken ein 7x7-Quadrat), und seit CDX-52 bekam es auch kein
Weiss-Band mehr — dessen Bedingung haengt seitdem an der Geometrie statt am
Zahlenverhaeltnis der Kanaele. CDX-52 ist richtig; ihm fehlte die Eingabe.

★★ **Der bekannte Nebenbefund ist hier die eigentliche Falle.** ``_save``
LOESCHT alle Modi und baut sie neu. Eine Angabe, die der Ladeweg nicht
mitliest, ist nach dem naechsten Speichern weg — fuer Builtins stellt
``ensure_builtins`` sie wieder her, ein Nutzerprofil verloere sie endgueltig.
Ein Test, der nur EINMAL speichert, wuerde das nicht sehen. Deshalb misst
:class:`ZweitesSpeichernTest` den zweiten Durchgang ueber einen NEU geoeffneten
Dialog — genau den Weg, den ein Nutzer geht, der sein Profil spaeter
nachbessert.

★ **Und die Messung endet nicht an der DB.** Der Zweck der Angabe ist, was der
Visualizer daraus macht; darum liest :class:`KetteBisZumVerbraucherTest` das
Ergebnis mit ``panel_grid_for``/``white_grid_for`` auf dem ECHTEN Weg wieder aus
(DB -> Modus -> Wert), so wie es ``_fixture_to_dict`` tut.

**Positivkontrollen** stehen in jedem Abschnitt: ein Profil OHNE Geometrie muss
ohne Geometrie bleiben (der Editor darf keine erfinden — sonst baekame jedes
selbstgebaute Panel ein Weiss-Band zurueck, das CDX-52 gerade abgeschafft hat),
und die uebrigen Profildaten duerfen die neue Eingabe nicht beschaedigen.

⚠️ **Was diese Datei NICHT behauptet.** Beim Schreiben ist ein FREMDER Befund
aufgefallen und gemessen worden: ``_save`` legt pro Modus nur den LETZTEN Kanal
an. In ``FixtureEditorDialog._save`` steht ``s.add(fc)`` eine Ebene zu weit
links und damit hinter der Kanalschleife statt darin — gemessen mit einem
152-Kanal-Panel: ``channel_count`` 152, tatsaechlich gespeicherte Kanaele 1.
Das ist unabhaengig von FM-23 (die Geometrie sitzt am Modus, nicht am Kanal),
gehoert aber gemeldet und nicht nebenbei geflickt. Deshalb prueft diese Datei
bewusst KEINE Kanalzahlen: ein Test, der das mitpruefte, waere entweder rot aus
fremdem Grund oder er fror den Befund als Sollzustand ein.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402
from sqlalchemy import select                                  # noqa: E402
from sqlalchemy.orm import Session, selectinload               # noqa: E402

from src.core.database import fixture_db as FDB                # noqa: E402
from src.core.database.fixture_db import get_engine            # noqa: E402
from src.core.database.models import (                         # noqa: E402
    FixtureMode, FixtureProfile, Manufacturer, PatchedFixture,
    create_all_idempotent)
from src.ui.widgets import fixture_editor as editor_module     # noqa: E402


_app = QApplication.instance() or QApplication([])

# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets wirklich
# abbauen (Muster + Begruendung: tests/_qt_lifecycle.py).
import pytest as _pytest_xplat15                               # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets        # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _panel_kanaele(zonen: int, weiss: int) -> list[dict]:
    """Kanalliste eines selbstgebauten Panels: N RGB-Zonen + M Weiss-Kanaele.

    Genau die Signatur aus dem CDX-52-Befund — aus ihr laesst sich die Form
    NICHT schliessen, deshalb geht es hier um die Eingabe."""
    chans: list[dict] = []
    for i in range(1, zonen + 1):
        for attr in ("color_r", "color_g", "color_b"):
            chans.append({"name": f"Zone {i} {attr}", "attribute": attr,
                          "default": 0, "highlight": 255})
    for k in range(1, weiss + 1):
        chans.append({"name": f"Weiss {k}", "attribute": "color_w",
                      "default": 0, "highlight": 255})
    return chans


class _EditorFall(unittest.TestCase):
    """Eigene Fixture-DB; Editor UND ``app_state`` sehen dieselbe."""

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.engine = get_engine(path)
        self.addCleanup(self.engine.dispose)
        create_all_idempotent(self.engine)

        # Der Editor holt seine Engine ueber den importierten Namen ...
        p1 = mock.patch.object(editor_module, "engine", lambda: self.engine)
        p1.start()
        self.addCleanup(p1.stop)
        # ... `app_state` (panel_grid_for/white_grid_for) ueber fixture_db._engine.
        p2 = mock.patch.object(FDB, "_engine", self.engine)
        p2.start()
        self.addCleanup(p2.stop)
        p3 = mock.patch.object(editor_module.QMessageBox, "information")
        p3.start()
        self.addCleanup(p3.stop)

        from src.core.app_state import clear_channel_cache
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)

    # ── Hilfen ──────────────────────────────────────────────────────────────

    def _neues_panel(self, *, grid=(0, 0), weiss=(0, 0), zonen=48, weiss_ch=8,
                     name="Selbstgebautes Panel", short="EIGEN48") -> int:
        """Legt ueber den ECHTEN Editor-Dialog ein Profil an. Gibt die ID."""
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText(name)
        dlg._edit_short.setText(short)
        dlg._cb_type.setCurrentText("matrix")
        tab = dlg._tabs.widget(0)
        tab.load_mode_data("Standard", _panel_kanaele(zonen, weiss_ch))
        tab.set_geometry(grid, weiss)
        dlg._save()
        return dlg._saved_id

    def _erneut_speichern(self, pid: int, *, neuer_name=None):
        """Oeffnet das Profil im Editor und speichert es NOCHMAL — der Weg, auf
        dem ``_save`` alle Modi verwirft und neu baut. Gibt den Dialog zurueck,
        damit der Aufrufer die geladenen Eingaben pruefen kann."""
        dlg = editor_module.FixtureEditorDialog(fixture_id=pid)
        self.addCleanup(dlg.deleteLater)
        if neuer_name is not None:
            dlg._edit_name.setText(neuer_name)
        return dlg

    def _form_nachtragen(self, pid: int, *, grid, weiss):
        """Traegt die Form ueber den ECHTEN Editor-Dialog nach und speichert.

        Bewusst OHNE `clear_channel_cache()` drumherum: dieser Weg soll den
        Cache selbst verwerfen — genau das ist die Zusage, die geprueft wird.
        """
        dlg = editor_module.FixtureEditorDialog(fixture_id=pid)
        self.addCleanup(dlg.deleteLater)
        dlg._tabs.widget(0).set_geometry(grid, weiss)
        dlg._save()
        return dlg

    def _modi(self, pid: int) -> dict:
        with Session(self.engine) as s:
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.id == pid)
            ).scalars().one()
            return {m.name: ((m.grid_rows, m.grid_cols),
                             (m.white_rows, m.white_cols))
                    for m in prof.modes}


# ════════════════════════════════════════════════════════════════════════════
# 1. Anlegen: der Editor schreibt die Form ueberhaupt erst
# ════════════════════════════════════════════════════════════════════════════

class AnlegenTest(_EditorFall):

    def test_neues_panel_bekommt_seine_rasterform(self):
        """Der Kern des Befunds: vorher landeten hier vier Nullen."""
        pid = self._neues_panel(grid=(4, 12), weiss=(1, 0))
        self.assertEqual(self._modi(pid)["Standard"], ((4, 12), (1, 0)))

    def test_positivkontrolle_ohne_angabe_bleibt_alles_null(self):
        """★ Der Editor darf keine Form ERFINDEN. Bekaeme ein Panel ohne
        Angabe eine, waere CDX-52 in der anderen Richtung entwertet: jedes
        selbstgebaute Profil haette wieder ein Weiss-Band."""
        pid = self._neues_panel(name="Panel ohne Angabe", short="EIGEN00")
        self.assertEqual(self._modi(pid)["Standard"], ((0, 0), (0, 0)))

    def test_positivkontrolle_uebrige_profildaten_unbeschaedigt(self):
        """Die neue Eingabe darf nichts verdraengen, was vorher schon ging —
        weder am Profil noch am Modus (der Modusname ist in diesem Projekt
        faktisch ein Schluessel, s. `_mode_eintrag`)."""
        pid = self._neues_panel(grid=(4, 12), weiss=(1, 0))
        with Session(self.engine) as s:
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes))
                .where(FixtureProfile.id == pid)
            ).scalars().one()
            mfr = s.get(Manufacturer, prof.manufacturer_id)
            self.assertEqual(
                (mfr.name, prof.name, prof.short_name, prof.fixture_type,
                 prof.source),
                ("Eigenbau", "Selbstgebautes Panel", "EIGEN48", "matrix",
                 "user"))
            self.assertEqual([(m.name, m.description) for m in prof.modes],
                             [("Standard", "")])


# ════════════════════════════════════════════════════════════════════════════
# 2. ★★ Zweites Speichern — `_save` verwirft alle Modi und baut sie neu
# ════════════════════════════════════════════════════════════════════════════

class ZweitesSpeichernTest(_EditorFall):

    def test_ladeweg_traegt_die_form_in_die_eingabe(self):
        """Ohne diesen Schritt gaebe es beim Speichern nichts zurueckzuschreiben
        — die Form haenge dann allein daran, dass der Nutzer sie jedes Mal neu
        eintippt."""
        pid = self._neues_panel(grid=(4, 12), weiss=(1, 0))
        dlg = self._erneut_speichern(pid)
        self.assertEqual(dlg._tabs.widget(0).get_geometry(), ((4, 12), (1, 0)))

    def test_form_ueberlebt_das_zweite_speichern(self):
        pid = self._neues_panel(grid=(4, 12), weiss=(1, 0))
        dlg = self._erneut_speichern(pid, neuer_name="Selbstgebautes Panel v2")
        dlg._save()
        with Session(self.engine) as s:
            self.assertEqual(s.get(FixtureProfile, pid).name,
                             "Selbstgebautes Panel v2")
        self.assertEqual(self._modi(pid)["Standard"], ((4, 12), (1, 0)))

    def test_form_ueberlebt_auch_das_dritte_speichern(self):
        """Idempotenz: der zweite Durchgang liest die Angabe aus einem Modus,
        den der erste erst geschrieben hat. Bricht das, bricht es hier."""
        pid = self._neues_panel(grid=(4, 12), weiss=(1, 0))
        self._erneut_speichern(pid)._save()
        self._erneut_speichern(pid)._save()
        self.assertEqual(self._modi(pid)["Standard"], ((4, 12), (1, 0)))

    def test_positivkontrolle_ohne_form_bleibt_es_beim_zweiten_mal_auch_dabei(self):
        pid = self._neues_panel(short="EIGEN00")
        self._erneut_speichern(pid)._save()
        self.assertEqual(self._modi(pid)["Standard"], ((0, 0), (0, 0)))

    def test_jeder_modus_behaelt_seine_eigene_form(self):
        """★ Die Form gehoert zum MODUS: dasselbe Geraet hat als 1-Zonen-Modus
        ein anderes Raster als als 48-Pixel-Modus. Eine Fassung, die nur EINE
        Form je Profil fuehrte, faellt hier um — und zwar erst nach dem
        Neuoeffnen, weil beide Modi dann aus der DB kommen."""
        dlg = editor_module.FixtureEditorDialog()
        self.addCleanup(dlg.deleteLater)
        dlg._cb_manufacturer.setCurrentText("Eigenbau")
        dlg._edit_name.setText("Zwei-Modi-Panel")
        dlg._edit_short.setText("EIGEN2M")
        dlg._cb_type.setCurrentText("matrix")
        dlg._tabs.widget(0).load_mode_data("Klein", _panel_kanaele(1, 1))
        dlg._tabs.widget(0).set_geometry((1, 1), (0, 0))
        dlg._add_mode(name="Gross", channels=_panel_kanaele(48, 8),
                      grid=(4, 12), weiss=(1, 0))
        dlg._save()
        pid = dlg._saved_id

        self._erneut_speichern(pid)._save()
        modi = self._modi(pid)
        self.assertEqual(modi["Klein"], ((1, 1), (0, 0)))
        self.assertEqual(modi["Gross"], ((4, 12), (1, 0)))


# ════════════════════════════════════════════════════════════════════════════
# 3. ★ Die Kette bis zum Verbraucher — DB -> Modus -> Wert
# ════════════════════════════════════════════════════════════════════════════

def _patched(profile_id, mode_name, channel_count):
    return PatchedFixture(fid=1, label="Panel", fixture_profile_id=profile_id,
                          mode_name=mode_name, universe=1, address=1,
                          channel_count=channel_count, fixture_type="matrix")


class KetteBisZumVerbraucherTest(_EditorFall):

    def test_eingetragene_form_kommt_beim_renderer_an(self):
        """Dasselbe Auflesen, das ``_fixture_to_dict`` benutzt. Ohne diesen
        Schritt behauptete der Test die Zustellung, statt sie zu messen."""
        from src.core.app_state import panel_grid_for, white_grid_for
        pid = self._neues_panel(grid=(4, 12), weiss=(1, 0))
        f = _patched(pid, "Standard", 152)
        self.assertEqual(panel_grid_for(f), (4, 12))
        self.assertEqual(white_grid_for(f), (1, 0))

    def test_die_form_kommt_an_OBWOHL_der_cache_schon_gefuellt_ist(self):
        """★★ Der Alltagsfall — und der einzige, der im Betrieb wirklich eintritt.

        Alle uebrigen Tests dieser Datei treffen einen LEEREN Cache: `setUp`
        ruft `clear_channel_cache()`, und das Profil wird im selben Test frisch
        angelegt, wurde also nie gezeichnet. Damit stellen sie per API einen
        Zustand her, den im Betrieb niemand herstellt.

        Real laeuft es andersherum: das Panel steht als geratenes Quadrat im
        3D — `_panel_grid_cache` ist also mit `(0, 0)` gefuellt —, und **genau
        deshalb** geht der Nutzer in den Editor und traegt 4x12 ein. Ohne
        `clear_channel_cache()` in `_save` liefert `panel_grid_for` danach
        weiter `(0, 0)`, bis jemand den Patch aendert oder das Programm neu
        startet. Der Nutzer sieht sein Panel unveraendert falsch und hat keinen
        Anhaltspunkt, warum.

        Gefunden von einer adversarialen Gegenpruefung; der Docstring von
        `clear_channel_cache` behauptete, Profil-Aenderungen aus
        „Generator/Editor" reisten ueber denselben Weg — die Editor-Haelfte
        stimmte nicht.
        """
        from src.core.app_state import panel_grid_for, white_grid_for
        # 1. Das Panel existiert und wurde schon einmal gezeichnet (ohne Form).
        pid = self._neues_panel(short="EIGENCACHE")
        f = _patched(pid, "Standard", 152)
        self.assertEqual(panel_grid_for(f), (0, 0),
                         "Vorbedingung: ohne Angabe raet der Renderer")
        self.assertEqual(white_grid_for(f), (0, 0))

        # 2. Der Nutzer traegt die Form nach — ueber den ECHTEN Editor-Dialog,
        #    und OHNE dass der Test den Cache anfasst.
        self._form_nachtragen(pid, grid=(4, 12), weiss=(1, 0))

        # 3. Der Renderer muss die neue Form sehen.
        self.assertEqual(
            panel_grid_for(f), (4, 12),
            "Die eingetragene Rasterform kommt nicht beim Renderer an — der "
            "Cache haelt den geratenen Wert fest. `_save` muss "
            "`clear_channel_cache()` rufen, wie es `fixture_generator._save` "
            "laengst tut.")
        self.assertEqual(white_grid_for(f), (1, 0),
                         "dasselbe fuer die Weiss-Leiste")

    def test_positivkontrolle_ohne_eingabe_raet_der_renderer_weiter(self):
        """``(0, 0)`` heisst bei der Rasterform WEITERRATEN und beim Weiss-Band
        NEIN — genau die CDX-52-Aussage. Der Editor darf daran nichts drehen."""
        from src.core.app_state import panel_grid_for, white_grid_for
        pid = self._neues_panel(short="EIGEN00")
        f = _patched(pid, "Standard", 152)
        self.assertEqual(panel_grid_for(f), (0, 0))
        self.assertEqual(white_grid_for(f), (0, 0))


if __name__ == "__main__":
    unittest.main()
