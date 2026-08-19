"""FM-14b (Nachbesserung) — EIN Name je Segment, an JEDER Flaeche.

Die erste Fassung von FM-14b hat die Programmer-GERAETELISTE umbenannt („Kopf 1"
-> „Grundfarbe", „Kopf 4" -> „Pixel 3") und dabei die Zwei-Namen-Lage erzeugt,
gegen die sie argumentierte: **dieselbe Zeile anklicken, und die Kopfzeile
darueber meldete `K4`** — dasselbe Segment, zwei Namen, zwei Zentimeter
auseinander. Gemessen vor der Nachbesserung (Spiider im 91-Kanal-Pixelmodus,
Kopf 3 gewaehlt):

    Geraeteliste        └ Pixel 3
    Kopfzeile           1 Gerät(e): [1] G1 · K4      <- zweiter Name
    Regler              Grundfarbe Shutter · K4      <- zweiter Name
    EFX-Zielliste       Fixture #1 · K4              <- zweiter Name
    Fan-Werkzeug        G1 · K4                      <- zweiter Name
    Command-Line        Selektiert: 1 (1·K4)         <- zweiter Name

Und mit Kopf 0 (der GRUNDFARBE) gewaehlt meldete die Kopfzeile `K1` — die Zusage
„Kopf 0 heisst im Programmer nicht mehr wie ein Pixel" war also nur fuer die
Liste eingeloest, nicht fuer den Programmer.

★ Diese Datei misst deshalb nicht eine Flaeche, sondern **alle Flaechen
gegeneinander**, jede ueber ihren echten Aufbau. Die Erwartung wird nirgends
hingeschrieben: sie kommt aus ``head_label_for_model`` / ``head_label_short``,
der EINEN Quelle. Ein Test, der die Namen selbst hinschreibt, wuerde die zweite
Quelle nur an eine dritte Stelle verschieben.

★★ **Dritte Runde.** Zwei weitere Pruefer haben auch die zweite Fassung nicht
freigegeben. Beide Ruegen sind nachgemessen und treffen zu — und beide fuehren
auf dieselbe Wurzel: **der Kopf-Index gehoert dem ATTRIBUT, nicht dem Geraet.**
``attr#N`` ist das N-te Vorkommen VON DIESEM Attribut. Am Pixel-Kopf sind die
Segmente die 20 Farb-Baenke; die 21 Rohkanaele zaehlen davon unabhaengig.

*Ruege 1* („wer den ersten Pixel greift, greift ins Falsche"), im Programmer
gemessen: mit Pixel 1 gewaehlt hiess der einzige Pro-Kopf-Regler ``Grundfarbe
Shutter · P1`` und schrieb ``raw#1`` = **DMX 9 = „Grundfarbe Rot Fein"**. Wer
das erste Pixel anfasste, verstellte die Grundfarbe — buchstaeblich.

*Ruege 2* (zwei Namen fuer ein Segment): ``attr_groups.attr_label`` uebersetzt
kontextfrei, also hiess Pixel 3 im Snap-Speichern-Dialog und beim
Kanal-Nachtragen weiter ``Rot (Kopf 4)``; die Grundfarbe hiess dort schlicht
``Rot`` und sah damit aus wie das erste Pixel.

Daraus die Trennung, die diese Datei misst: **Segmentname** nur dort, wo der
Kopf-Index wirklich ein Segment adressiert (Abschnitte 3-6, 8) — sonst der
**Kanalname** dessen, was der Regler wirklich schreibt (Abschnitt 7).

★★ **Positivkontrolle durchgehend am MOVBAR4** — VIER Farb-Baenke, also nicht
schon an der Bank-Zahl aussortiert, nur eben kein Pixel-Kopf. Fuer ihn stehen die
Erwartungen als **wortwoertliche Bestandsstrings** in dieser Datei (nicht aus der
Quelle abgeleitet): genau so muss es nach der Aenderung noch aussehen.
"""
from __future__ import annotations

import json
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                    # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402
from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session, selectinload                 # noqa: E402

from _fixture_quelle import frische_library                      # noqa: E402
from src.core.app_state import (                                 # noqa: E402
    head_label_for_model, head_label_gemeinsam, head_label_short,
    head_models_by_fid)
from src.core.database.models import (                           # noqa: E402
    FixtureProfile, PatchedFixture)

_PIXEL_MODE = "91-Kanal Pixel RGB (Mode 7)"
_PIXEL_CH = 91
_MOVBAR_MODE = "22-Kanal 4×Move RGB"
_MOVBAR_CH = 22
_PIXEL_MODELL = "pixel_head"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ════════════════════════════════════════════════════════════════════════════
# 1. Die EINE Quelle — gibt es wirklich nur eine Regel?
# ════════════════════════════════════════════════════════════════════════════

class EineQuelleTest(unittest.TestCase):
    """``head_label_short`` muss die ABGEKUERZTE ``head_label_for_model`` sein.

    Waere es eine zweite Regel, koennten weite und enge Flaechen denselben Kopf
    verschieden nennen — und genau das ist der Fehler, um den es geht."""

    def _kurz_aus_voll(self, voll: str) -> str:
        """Die Abkuerzungsregel, unabhaengig vom Produktionscode formuliert:
        eine Beschriftung MIT Nummer wird Anfangsbuchstabe + Nummer, eine ohne
        Nummer die ersten zwei Buchstaben."""
        ziffern = re.sub(r"\D", "", voll)
        if ziffern:
            return f"{voll[0].upper()}{ziffern}"
        return voll[:2].upper()

    def test_die_kurzform_ist_die_vollform_abgekuerzt(self):
        """Fuer BEIDE Beschriftungen und jeden Kopf, den ein Geraet haben kann."""
        for modell in ("", _PIXEL_MODELL, "spider", "moving_head"):
            for h in range(0, 26):
                voll = head_label_for_model(modell, h)
                self.assertEqual(
                    head_label_short(modell, h), self._kurz_aus_voll(voll),
                    f"Kurzform und Vollform laufen auseinander "
                    f"(Modell {modell!r}, Kopf {h}): {voll!r}")

    def test_die_grundfarbe_traegt_keine_pixelnummer(self):
        """★ Ruege 1, als reine Bedingung: was Kopf 0 am Pixel-Kopf auch heisst
        — es darf nicht wie ein Pixel aussehen. Sonst greift, wer „das erste
        Pixel" sucht, ins ganze Geraet."""
        for name in (head_label_for_model(_PIXEL_MODELL, 0),
                     head_label_short(_PIXEL_MODELL, 0)):
            self.assertNotRegex(name, r"(?i)pixel|^P\d")
            self.assertNotIn(name, {head_label_for_model(_PIXEL_MODELL, n)
                                    for n in range(1, 30)})
            self.assertNotIn(name, {head_label_short(_PIXEL_MODELL, n)
                                    for n in range(1, 30)})


# ════════════════════════════════════════════════════════════════════════════
# 2. Das Rig: ein Pixel-Kopf und ein ringloses Vier-Kopf-Geraet
# ════════════════════════════════════════════════════════════════════════════

class _RigFall(unittest.TestCase):
    """Frische Bibliothek (FIXTEST-FRESH) + leere Show, gepatcht ueber den
    echten ``AppState.add_fixture``."""

    def setUp(self):
        from src.core.app_state import clear_channel_cache, get_state
        from src.core.show.show_file import reset_show
        _app()
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)
        reset_show()
        self.addCleanup(reset_show)
        self.state = get_state()
        self.spiider = self._patch("SPIIDER", _PIXEL_MODE, _PIXEL_CH,
                                   fid=1, adresse=1)
        self.movbar = self._patch("MOVBAR4", _MOVBAR_MODE, _MOVBAR_CH,
                                  fid=2, adresse=200)

    def _patch(self, short, mode, chans, *, fid, adresse):
        with Session(self._eng) as s:
            p = s.execute(select(FixtureProfile).options(
                selectinload(FixtureProfile.modes)).where(
                FixtureProfile.short_name == short)).scalars().first()
            self.assertIsNotNone(p, f"Profil {short} fehlt in der Bibliothek")
            pid = int(p.id)
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"G{fid}", fixture_profile_id=pid, mode_name=mode,
            universe=1, address=adresse, channel_count=chans,
            fixture_type="moving_head"), undoable=False)
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    # ── Die Flaechen, jede ueber ihren ECHTEN Aufbau ──────────────────────────

    def _programmer_auf(self, fid: int, head: int):
        """Programmer mit genau dieser Kopf-Zelle gewaehlt — echter Aufbau
        (``_refresh_fixture_list``) und echte Auswahl-Naht. Gibt
        ``(view, Listenzeile)`` zurueck."""
        from src.ui.views.programmer_view import ProgrammerView
        view = ProgrammerView()
        self.addCleanup(view.deleteLater)
        lst = view._fixture_list
        zelle = f"{fid}:{head}"
        treffer = None
        for i in range(lst.count()):
            it = lst.item(i)
            passt = it.data(Qt.ItemDataRole.UserRole) == zelle
            it.setSelected(passt)
            if passt:
                treffer = it
        self.assertIsNotNone(treffer, f"keine Zeile fuer {zelle}")
        view._on_fixture_selected()
        # ★ Der Tab-Aufbau raeumt die alten Regler per ``deleteLater`` weg — das
        # wirkt erst, wenn die Ereignisschlange laeuft. Ohne diesen Schritt
        # findet ``findChildren`` die Regler des VORIGEN Aufbaus mit und der
        # Test misst Leichen (gemessen: derselbe Regler zweimal, der zweite
        # schrieb dann nichts mehr).
        from PySide6.QtCore import QEvent
        _app().sendPostedEvents(None, QEvent.Type.DeferredDelete)
        return view, treffer

    def _programmer(self, fid: int, head: int) -> dict:
        """Die drei Programmer-Flaechen, die ein SEGMENT benennen: Zeile in der
        Geraeteliste, Kopfzeile darueber und der FARB-Regler dieses Kopfes.

        ★ Der Farbregler ist die Probe, dass „P3" keine Erfindung dieser
        Ansicht ist: er traegt den Kanalnamen aus der Bibliothek
        (``P3 Rot``/``Grundfarbe Rot``), waehrend die anderen Flaechen ihn aus
        ``head_label_*`` bauen. Laufen die beiden auseinander, faellt es hier
        auf. Die uebrigen Pro-Kopf-Regler benennen KEIN Segment mehr (ihr
        Kopf-Index adressiert keins) — sie werden in ``_kopfregler`` gemessen."""
        from src.ui.views.programmer_view import AttributeSlider
        view, treffer = self._programmer_auf(fid, head)
        farbe = sorted({w._channel.name for w in view.findChildren(AttributeSlider)
                        if w._display_name is None and w._head == head
                        and (w._channel.attribute or "").startswith("color_")
                        and all(getattr(f, "fid", None) == fid
                                for f in w._fixtures)})
        self.assertTrue(farbe, f"kein Farbregler fuer {fid}:{head}")
        return {"Programmer-Geraeteliste": treffer.text().strip(),
                "Programmer-Kopfzeile": view._lbl_selection.text(),
                "Programmer-Farbregler": farbe[0]}

    def _kopfregler(self, fid: int, head: int) -> list:
        """Die Pro-Kopf-Regler MIT eigener Beschriftung (die generischen, nicht
        die Farbregler) — sortiert, nur die dieses einen Geraets."""
        from src.ui.views.programmer_view import AttributeSlider
        view, _ = self._programmer_auf(fid, head)
        return sorted({w._display_name for w in view.findChildren(AttributeSlider)
                       if w._display_name and w._head == head
                       and all(getattr(f, "fid", None) == fid
                               for f in w._fixtures)})

    def _snap_flaechen(self, fid: int, head: int) -> dict:
        """Die zwei Snap-Flaechen, die einen Kanal ueber seinen Kopf benennen:
        der Speichern-Dialog (``ChannelSelectDialog``) und „➕ Kanal" im
        Snap-Editor. Beide liefen ueber die kontextfreie ``attr_label`` und
        nannten Pixel 3 „Rot (Kopf 4)".

        Gefahren wird der ECHTE Weg: der Speichern-Dialog baut seine Liste im
        Konstruktor, „➕ Kanal" laeuft durch ``_add_channel`` (das die Geraete
        des Typs selbst zusammensucht) — nur der modale ``exec()`` wird
        abgefangen, sonst haenge der Test."""
        from src.core.app_state import (get_channels_for_patched,
                                        programmer_key_for_head)
        from src.core.engine.snap_library import get_snap_library
        from src.ui.views import snap_editor as SE
        from src.ui.views.snap_file_panel import ChannelSelectDialog
        from PySide6.QtWidgets import QDialog
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == fid)
        key = programmer_key_for_head(get_channels_for_patched(fx), "color_r", head)

        dlg = ChannelSelectDialog({fid: {key: 200}})
        self.addCleanup(dlg.deleteLater)
        self.assertIn(key, dlg._attr_checks, f"kein Kanal-Haken fuer {key}")

        snap = get_snap_library().add_snap(f"FM14b {fid}:{head}", "",
                                           {fid: {"intensity": 255}})
        self.addCleanup(get_snap_library().remove_snap, snap.id)
        ed = SE.SnapEditor(snap)
        self.addCleanup(ed.deleteLater)
        gefangen = []
        orig = SE._AddChannelDialog

        class _Fang(orig):
            def exec(self):                       # noqa: A003 (Qt-Name)
                gefangen.append(self)
                return QDialog.DialogCode.Rejected

        SE._AddChannelDialog = _Fang
        try:
            ed._add_channel(("typ",), [fid])
        finally:
            SE._AddChannelDialog = orig
        self.assertTrue(gefangen, "der Nachtragen-Dialog wurde gar nicht gebaut")
        haken = gefangen[0]._checks.get(key)
        self.assertIsNotNone(haken, f"{key} steht nicht zum Nachtragen bereit")
        return {"Snap-Speichern-Dialog": dlg._attr_checks[key].text(),
                "Snap-Kanal-nachtragen": haken.text()}

    def _raster(self, fid: int, head: int) -> dict:
        """Rasterzelle + ihr Tooltip im Gruppen-Editor, ueber den echten Aufbau
        (``_refresh_fixtures`` laeuft im Konstruktor)."""
        from src.ui.views.fixture_group_view import FixtureGroupView
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        g = view._grid_widget
        return {"Gruppen-Rasterzelle": g.zell_beschriftung(f"{fid}:{head}"),
                "Gruppen-Raster-Tooltip": g.zell_tooltip(f"{fid}:{head}")}

    def _matrix(self, fid: int, head: int) -> dict:
        """Zell-Tooltip der Matrix-Vorschau — ueber den echten Weg: Kopf-Gruppe
        waehlen, ``+ Neu``, Raster aus der Gruppe binden.

        Liefert NICHTS, wenn dieser Kopf gar keine Rasterzelle hat: die
        Grundfarbe steht bewusst nicht im Ring-Raster (FM-14b), es gibt an
        dieser Flaeche also kein Segment zu benennen. Der Aufrufer prueft die
        Zahl der Flaechen, damit ein stilles Verschwinden auffaellt."""
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        gid = self.state.find_head_matrix_group(fid, dedicated=True)
        self.assertIsNotNone(gid, "beim Patchen entstand keine Kopf-Matrix")
        with self.state._session() as s:
            from src.core.database.models import FixtureGroup
            pos = json.loads(s.get(FixtureGroup, gid).positions_json or "{}")
        zelle = next((k for k, v in pos.items() if v == f"{fid}:{head}"), None)
        if zelle is None:
            return {}
        self.state.set_selected_group_id(gid)
        mv = RgbMatrixView()
        self.addCleanup(mv.deleteLater)
        mv._add()
        mv._assign_from_selection()
        self.assertIsNotNone(mv._current, "keine Matrix angelegt")
        c, r = (int(x) for x in zelle.split(","))
        return {"Matrix-Vorschau-Tooltip":
                mv._preview.assignment_text(r * mv._current.cols + c)}

    def _efx(self, fid: int, head: int) -> dict:
        """EFX-Zielliste — ueber den echten ``_add_efx`` (Auto-Zuweisung aus der
        Auswahl), nicht ueber einen Aufruf der Beschriftungsfunktion."""
        from src.ui.views.efx_view import EfxView
        self.state.set_selected_cells([f"{fid}:{head}"])
        view = EfxView()
        self.addCleanup(view.deleteLater)
        vorher = {i.id for i in view._instances}
        view._add_efx()
        self.addCleanup(lambda: [view._fm.remove(i.id)
                                 for i in list(view._instances)
                                 if i.id not in vorher])
        zeilen = [view._fx_list.item(i).text()
                  for i in range(view._fx_list.count())]
        self.assertEqual(len(zeilen), 1, f"EFX-Ziele: {zeilen}")
        return {"EFX-Zielliste": zeilen[0]}

    def _fan(self, fid: int, head: int) -> dict:
        """Fan-Werkzeug — ueber ``set_cells``, den Weg der Kopf-Auswahl."""
        from src.ui.widgets.fan_tool import FanTool
        w = FanTool()
        self.addCleanup(w.deleteLater)
        w.set_cells([f"{fid}:{head}"])
        self.assertEqual(w._table.rowCount(), 1)
        return {"Fan-Werkzeug": w._table.item(0, 1).text()}

    def _cmdline(self, fid: int, head: int) -> dict:
        """Command-Line-Statuszeile — ueber den echten Parser und den echten
        State (getippt wird 1-basiert: ``1:4`` ist Kopf-Index 3)."""
        from src.core.cmdline.parser import parse
        res = parse(f"{fid}:{head + 1}").execute(self.state)
        self.assertTrue(res.ok, res.message)
        return {"Command-Line-Statuszeile": res.message}

    def alle_flaechen(self, fid: int, head: int) -> dict:
        """ALLE Flaechen, die ein SEGMENT benennen — je Flaeche ihr echter
        Aufbau. Nicht dabei: die Pro-Kopf-Regler ohne Segment-Bezug
        (``_kopfregler``), die benennen einen KANAL und werden eigens
        gemessen."""
        out = {}
        for teil in (self._programmer(fid, head), self._raster(fid, head),
                     self._matrix(fid, head), self._efx(fid, head),
                     self._fan(fid, head), self._cmdline(fid, head),
                     self._snap_flaechen(fid, head)):
            out.update(teil)
        return out


# ════════════════════════════════════════════════════════════════════════════
# 3. ★ Der Kern: dasselbe Segment, ueberall derselbe Name
# ════════════════════════════════════════════════════════════════════════════

class PixelKopfBenennungTest(_RigFall):

    def _pruefe(self, head: int):
        """Jede Flaeche nennt den Kopf entweder ausgeschrieben oder in der EINEN
        abgeleiteten Kurzform — und KEINE nennt ihn nach seinem Index."""
        voll = head_label_for_model(_PIXEL_MODELL, head)
        kurz = head_label_short(_PIXEL_MODELL, head)
        index_voll = head_label_for_model("", head)      # „Kopf N+1"
        index_kurz = head_label_short("", head)          # „KN+1"
        flaechen = self.alle_flaechen(1, head)
        # 11 Flaechen; die Grundfarbe hat bewusst KEINE Rasterzelle und damit
        # auch keinen Matrix-Tooltip (FM-14b) — sonst zoege jeder Effekt sie mit.
        self.assertEqual(len(flaechen), 10 if head == 0 else 11, sorted(flaechen))
        for name, text in flaechen.items():
            with self.subTest(flaeche=name):
                self.assertTrue(
                    re.search(rf"(?<![\w]){re.escape(voll)}(?![\w])", text)
                    or re.search(rf"(?<![\w]){re.escape(kurz)}(?![\w])", text),
                    f"{name} nennt Kopf {head} weder {voll!r} noch {kurz!r}: "
                    f"{text!r}")
                self.assertNotRegex(
                    text, rf"(?<![\w]){re.escape(index_voll)}(?![\w])",
                    f"{name} nennt Kopf {head} nach seinem INDEX ({index_voll}) "
                    f"— das ist der zweite Name: {text!r}")
                self.assertNotRegex(
                    text, rf"(?<![\w]){re.escape(index_kurz)}(?![\w])",
                    f"{name} nennt Kopf {head} nach seinem INDEX ({index_kurz}) "
                    f"— das ist der zweite Name: {text!r}")
        return flaechen

    def test_pixel_3_heisst_ueberall_gleich(self):
        """★★ Ruege 2, gemessen: an KEINER Flaeche mehr „K4" neben „Pixel 3"."""
        self._pruefe(3)

    def test_das_letzte_pixel_heisst_ueberall_gleich(self):
        """Der andere Rand des Rings (Pixel 19 = Kopf 19) — dort ist die
        Verschiebung um eins am leichtesten zu uebersehen."""
        self._pruefe(19)

    def test_die_grundfarbe_heisst_ueberall_gleich_und_nach_keinem_pixel(self):
        """★★ Ruege 1, gemessen: Kopf 0 heisst an KEINER Flaeche wie ein Pixel
        — auch nicht in der Kopfzeile, wo bis hierhin „K1" stand."""
        flaechen = self._pruefe(0)
        pixelnamen = {head_label_for_model(_PIXEL_MODELL, n)
                      for n in range(1, 20)} | {
                      head_label_short(_PIXEL_MODELL, n) for n in range(1, 20)}
        for name, text in flaechen.items():
            with self.subTest(flaeche=name):
                for p in pixelnamen:
                    self.assertNotRegex(
                        text, rf"(?<![\w]){re.escape(p)}(?![\w])",
                        f"{name} nennt die GRUNDFARBE {p!r}: {text!r}")

    def test_die_kopfzeile_folgt_der_zeile_die_man_angeklickt_hat(self):
        """★ Die Stelle, an der die erste Fassung scheiterte: Liste und Kopfzeile
        stehen uebereinander im selben Fenster. Gemessen wird ihr VERHAELTNIS,
        nicht zweimal derselbe Text."""
        for head in (0, 3, 19):
            with self.subTest(head=head):
                p = self._programmer(1, head)
                zeile = p["Programmer-Geraeteliste"].lstrip("└ ").strip()
                self.assertEqual(zeile, head_label_for_model(_PIXEL_MODELL, head))
                self.assertTrue(
                    p["Programmer-Kopfzeile"].endswith(
                        f"· {head_label_short(_PIXEL_MODELL, head)}"),
                    f"Zeile {zeile!r}, Kopfzeile {p['Programmer-Kopfzeile']!r}")

    def test_die_enge_rasterzelle_nennt_den_vollen_namen_im_tooltip(self):
        """Die Rasterzelle ist die EINZIGE Flaeche, auf die nur eine Kurzform
        passt. Damit „P3" dort keine Sackgasse ist, steht der volle Name im
        Tooltip derselben Zelle."""
        for head in (0, 3, 19):
            with self.subTest(head=head):
                r = self._raster(1, head)
                self.assertEqual(r["Gruppen-Rasterzelle"],
                                 f"1·{head_label_short(_PIXEL_MODELL, head)}")
                self.assertEqual(r["Gruppen-Raster-Tooltip"],
                                 f"G1 · {head_label_for_model(_PIXEL_MODELL, head)}")

    def test_der_tooltip_kommt_beim_ueberfahren_wirklich_an(self):
        """★★ Die VIZ-51-Frage („Feld vorhanden, Nutzlast leer"): der Test
        darueber ruft die Methode selbst auf. Hier faehrt der echte Weg — Maus
        ueber die Zelle, Tooltip vom Widget zurueckgelesen."""
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QMouseEvent
        from src.ui.views.fixture_group_view import FixtureGroupView
        view = FixtureGroupView()
        self.addCleanup(view.deleteLater)
        g = view._grid_widget
        self.assertTrue(g.hasMouseTracking(),
                        "ohne Mausverfolgung liefert Qt gar keine Bewegung "
                        "ohne gedrueckte Taste — der Tooltip erschiene nie")
        g.set_grid(4, 1)
        g.positions = {(0, 0): "1:3"}
        g.resize(400, 100)
        cw, ch = g.cell_size()
        pos = QPointF(cw / 2, ch / 2)
        ev = QMouseEvent(QEvent.Type.MouseMove, pos, pos,
                         Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        g.mouseMoveEvent(ev)
        self.assertEqual(g.toolTip(),
                         f"G1 · {head_label_for_model(_PIXEL_MODELL, 3)}")

    def test_eine_leere_zelle_zeigt_keinen_tooltip(self):
        """POSITIVKONTROLLE zum Tooltip: ueber einer freien Zelle bleibt der
        alte Text nicht stehen (sonst benennt das Raster eine Zelle, die es
        gar nicht gibt)."""
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QMouseEvent
        from src.ui.views.fixture_group_view import FixtureGridWidget
        g = FixtureGridWidget()
        self.addCleanup(g.deleteLater)
        g.update_fixture_labels({1: "G1"}, {1: _PIXEL_MODELL})
        g.set_grid(4, 1)
        g.positions = {(0, 0): "1:3"}
        g.resize(400, 100)
        cw, ch = g.cell_size()

        def _fahre(x):
            pos = QPointF(x, ch / 2)
            g.mouseMoveEvent(QMouseEvent(
                QEvent.Type.MouseMove, pos, pos,
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier))

        _fahre(cw / 2)
        self.assertTrue(g.toolTip())
        _fahre(cw * 2.5)                       # freie Zelle
        self.assertEqual(g.toolTip(), "")


# ════════════════════════════════════════════════════════════════════════════
# 4. ★★ POSITIVKONTROLLE: ein Geraet OHNE Ringe bleibt Wort fuer Wort
# ════════════════════════════════════════════════════════════════════════════

class OhneRingeUnveraendertTest(_RigFall):
    """MOVBAR4: vier Farb-Baenke, also nicht schon an der Bank-Zahl aussortiert
    — nur eben kein Pixel-Kopf. Die Erwartungen stehen hier BEWUSST als
    wortwoertliche Bestandsstrings, nicht aus der Quelle abgeleitet: eine
    abgeleitete Erwartung wuerde jede Umbenennung mitmachen."""

    def test_jede_flaeche_bleibt_wort_fuer_wort(self):
        flaechen = self.alle_flaechen(2, 3)
        self.assertEqual(flaechen, {
            "Programmer-Geraeteliste": "└ Kopf 4",
            "Programmer-Kopfzeile": "1 Gerät(e): [2] G2 · K4",
            "Programmer-Farbregler": "Kopf 4 Blau",
            "Gruppen-Rasterzelle": "2·K4",
            "Gruppen-Raster-Tooltip": "G2 · Kopf 4",
            "Matrix-Vorschau-Tooltip": "G2 · Kopf 4",
            "EFX-Zielliste": "Fixture #2 · K4  offset=0.00",
            "Fan-Werkzeug": "G2 · K4",
            "Command-Line-Statuszeile": "Selektiert: 1 (2·K4)",
            "Snap-Speichern-Dialog": "Rot (Kopf 4)  (1)",
            "Snap-Kanal-nachtragen": "Rot (Kopf 4)  ·  Color",
        })

    def test_auch_die_pro_kopf_regler_bleiben_wort_fuer_wort(self):
        """★★ Die Flaeche, an der sich am Pixel-Kopf am meisten aendert: dort
        traegt ein Regler ohne Segment-Bezug jetzt den Namen des Kanals, den er
        schreibt. Hier darf davon NICHTS ankommen — inklusive des bekannten
        Schoenheitsfehlers, dass der Kanalname von der VORLAGE stammt
        („Kopf 1 Pan · K4"). Ihn hier mitzukorrigieren waere eine Aenderung an
        einem ringlosen Geraet."""
        self.assertEqual(self._kopfregler(2, 3),
                         ["Kopf 1 Pan · K4", "Kopf 1 Tilt · K4"])
        self.assertEqual(self._kopfregler(2, 0),
                         ["Kopf 1 Pan · K1", "Kopf 1 Tilt · K1",
                          "Master Dimmer · K1", "Shutter/Strobe · K1"])

    def test_auch_der_erste_kopf_bleibt_kopf_1(self):
        """Kopf 0 heisst hier weiter „Kopf 1" — die Grundfarben-Regel darf NICHT
        auf gewoehnliche Mehrkopf-Geraete ausschlagen."""
        flaechen = self.alle_flaechen(2, 0)
        self.assertEqual(flaechen["Programmer-Geraeteliste"], "└ Kopf 1")
        self.assertEqual(flaechen["Gruppen-Rasterzelle"], "2·K1")
        self.assertEqual(flaechen["Command-Line-Statuszeile"],
                         "Selektiert: 1 (2·K1)")
        # Der erste Kopf traegt am ringlosen Geraet KEIN Suffix — genau wie
        # bisher („Rot", nicht „Rot (Kopf 1)").
        self.assertEqual(flaechen["Snap-Speichern-Dialog"], "Rot  (1)")
        for text in flaechen.values():
            self.assertNotIn("Grundfarbe", text)
            self.assertNotIn("Pixel", text)

    def test_die_fehlermeldung_der_command_line_bleibt_wort_fuer_wort(self):
        """Die Kopf-Spanne einer Fehlermeldung kommt jetzt aus der EINEN Quelle.
        Am ringlosen Geraet muss dabei buchstabengleich derselbe Text
        herauskommen."""
        from src.core.cmdline.parser import parse
        res = parse("2:9 red 255").execute(self.state)
        self.assertFalse(res.ok)
        self.assertEqual(
            res.message,
            "Gerät 2 hat für 'color_r' 4 Köpfe (K1–K4) — K9 gibt es dort nicht")


# ════════════════════════════════════════════════════════════════════════════
# 5. Der gemeinsame Regler — ein Regler, zwei Geraetearten
# ════════════════════════════════════════════════════════════════════════════

class GemischterReglerTest(_RigFall):
    """Ein Pro-Kopf-Regler traegt oft MEHRERE Geraete. Sind sie verschiedener
    Art, benennt er kein einzelnes Segment mehr, sondern den Kopf-INDEX, den
    alle gemeinsam haben — ein Pixel-Name waere fuer die Mover-Bar falsch."""

    def test_einheitliche_auswahl_bekommt_den_segmentnamen(self):
        self.assertEqual(head_label_gemeinsam([self.spiider], 3, kurz=True),
                         head_label_short(_PIXEL_MODELL, 3))
        self.assertEqual(head_label_gemeinsam([self.spiider], 3),
                         head_label_for_model(_PIXEL_MODELL, 3))

    def test_ringloses_geraet_behaelt_die_indexbeschriftung(self):
        self.assertEqual(head_label_gemeinsam([self.movbar], 3, kurz=True),
                         head_label_short("", 3))

    def test_gemischte_auswahl_faellt_auf_den_index_zurueck(self):
        """★ Mit ZWEI Partnern und in BEIDEN Reihenfolgen. „Nimm irgendeines der
        Modelle" wuerde sonst je nach Sortierung zufaellig richtig aussehen: der
        Spiider heisst ``pixel_head``, die Mover-Bar sortiert davor, der Spider
        dahinter — eine Auswahl kann also nicht beide Male am Rand stehen."""
        spider = self._patch("SPIDER14", "14-Kanal", 14, fid=5, adresse=500)
        from src.core.app_state import viz_model_for
        self.assertNotEqual(viz_model_for(spider), viz_model_for(self.movbar),
                            "beide Partner haben dasselbe Modell — der Test "
                            "koennte eine Sortier-Wahl nicht mehr entlarven")
        for partner in (self.movbar, spider):
            for paar in ([self.spiider, partner], [partner, self.spiider]):
                with self.subTest(partner=partner.fid,
                                  reihenfolge=[f.fid for f in paar]):
                    self.assertEqual(head_label_gemeinsam(paar, 3, kurz=True),
                                     head_label_short("", 3))

    def test_ohne_geraete_bleibt_es_beim_index(self):
        self.assertEqual(head_label_gemeinsam([], 3), head_label_for_model("", 3))

    def _tilt_regler(self, *, pixel: bool) -> list:
        """Die Pro-Bar-Tilt-Regler eines Doppeltilters — ueber den ECHTEN
        Position-Tab. Sie entstehen nur bei GEMISCHTER Auswahl (Spider +
        Moving Head); eine reine Spider-Auswahl bekommt stattdessen das
        SpiderPositionTool."""
        from src.ui.views.programmer_view import ProgrammerView, AttributeSlider
        from src.core.app_state import clear_channel_cache
        if pixel:
            with Session(self._eng) as s:
                p = s.execute(select(FixtureProfile).where(
                    FixtureProfile.short_name == "SPIDER14")).scalars().one()
                p.viz_model = _PIXEL_MODELL
                s.commit()
            clear_channel_cache()
        spider = self._patch("SPIDER14", "14-Kanal", 14, fid=4, adresse=400)
        view = ProgrammerView()
        self.addCleanup(view.deleteLater)
        lst = view._fixture_list
        for i in range(lst.count()):
            it = lst.item(i)
            it.setSelected(it.data(Qt.ItemDataRole.UserRole)
                           in (str(spider.fid), str(self.movbar.fid)))
        view._on_fixture_selected()
        namen = list(dict.fromkeys(
            w._display_name for w in view.findChildren(AttributeSlider)
            if w._display_name and w._channel.attribute == "tilt"
            and [getattr(f, "fid", None) for f in w._fixtures] == [spider.fid]))
        self.assertEqual(len(namen), 2, f"zwei Bar-Regler erwartet: {namen}")
        return namen

    def test_die_bar_regler_eines_pixel_doppeltilters_nennen_ihren_kanal(self):
        """★ Der zweite ``· K{n+1}``-Regler im Programmer. Ein Doppeltilter mit
        ausdruecklich gesetztem ``viz_model = 'pixel_head'`` (Fixture-Generator)
        hat ZWEI Farb-Baenke — die TILT-Achsen zaehlen davon unabhaengig. „Tilt
        Bar Rechts · P1" behauptete also Pixel 1, obwohl der Regler die zweite
        Bar kippt. Jetzt steht dort der Kanal, den er wirklich schreibt; ein
        Segment nennt er gar nicht mehr."""
        namen = self._tilt_regler(pixel=True)
        self.assertEqual(namen, ["Tilt Bar Links", "Tilt Bar Rechts"])
        for name in namen:
            for h in (0, 1):
                self.assertNotIn(head_label_short(_PIXEL_MODELL, h), name)

    def test_die_bar_regler_eines_gewoehnlichen_doppeltilters_bleiben(self):
        """POSITIVKONTROLLE: derselbe Spider OHNE Override — Wort fuer Wort wie
        bisher."""
        self.assertEqual(self._tilt_regler(pixel=False),
                         ["Tilt Bar Links · K1", "Tilt Bar Rechts · K2"])

    def test_der_regler_im_programmer_zeigt_das_auch(self):
        """★ Gemessen an der Flaeche, nicht nur an der Funktion: beide Geraete
        auf Kopf 3 eingeschraenkt, ein Regler traegt beide."""
        from src.ui.views.programmer_view import ProgrammerView, AttributeSlider
        # MYTHOS: kein Pixel-Kopf, hat aber (wie der Spiider) mehr als vier
        # Kanaele desselben rohen Attributs — nur dann landen beide Geraete im
        # SELBEN Kopf-Regler. Die Kopf-Einschraenkung kommt ueber die
        # Zell-Auswahl, also den Weg, den Gruppen-Raster und Command-Line gehen.
        mythos = self._patch("MYTHOS", "30-Kanal (Standard)", 30,
                             fid=3, adresse=400)
        view = ProgrammerView()
        self.addCleanup(view.deleteLater)
        # Erst die View, dann die Auswahl: der Listen-Neuaufbau im Konstruktor
        # veroeffentlicht eine leere Auswahl und wuerde die Zellen sonst wieder
        # loeschen.
        self.state.set_selected_cells(["1:3", f"{mythos.fid}:3"])
        view._sync_follow_selection()
        self.assertEqual(self.state.selected_heads_for(1), {3},
                         "die Kopf-Einschraenkung kam gar nicht an")
        gemischt = [w._display_name for w in view.findChildren(AttributeSlider)
                    if w._display_name and w._head == 3
                    and {getattr(f, "fid", None) for f in w._fixtures} == {1, 3}]
        self.assertTrue(gemischt, "kein Regler ueber beide Geraete")
        for name in gemischt:
            self.assertTrue(name.endswith(f"· {head_label_short('', 3)}"),
                            f"{name!r} nennt einen gemeinsamen Regler nach EINEM "
                            f"der beiden Geraete")


# ════════════════════════════════════════════════════════════════════════════
# 6. Die Nutzlast — kommt das Modell an den fid-Flaechen wirklich an?
# ════════════════════════════════════════════════════════════════════════════

class NutzlastTest(_RigFall):
    """★★ Die VIZ-51-Lehre: „Feld vorhanden, Funktion richtig, Nutzlast leer".
    EFX-Liste, Fan-Werkzeug und Command-Line halten nur fids — sie MUESSEN das
    Render-Modell von aussen bekommen."""

    def test_die_modellkarte_kennt_beide_geraete(self):
        m = head_models_by_fid()
        self.assertEqual(m.get(1), _PIXEL_MODELL)
        # MOVBAR4 hat ein Modell — nur eben nicht das des Pixel-Kopfes. Genau
        # das entscheidet die Beschriftung; „irgendein Modell" reicht nicht.
        self.assertTrue(m.get(2))
        self.assertNotEqual(m.get(2), _PIXEL_MODELL)
        self.assertEqual(head_label_short(m[2], 3), head_label_short("", 3))

    def test_ohne_modellkarte_bleibt_es_bei_der_indexbeschriftung(self):
        """POSITIVKONTROLLE: ein Aufrufer ohne Modell-Angabe (Alt-Pfad, Test-Fake)
        bekommt weiter die Bestandsbeschriftung — die Aenderung ist additiv."""
        from src.ui.views.efx_view import EfxView
        from src.core.engine.efx import EfxFixture
        self.assertEqual(EfxView._target_label(EfxFixture(fid=1, head=3)),
                         f"Fixture #1 · {head_label_short('', 3)}")

    def _efx_zeilen(self, view) -> list:
        return [view._fx_list.item(i).text()
                for i in range(view._fx_list.count())]

    def _efx_view(self, *, follow: bool):
        from src.ui.views.efx_view import EfxView
        view = EfxView(follow_selection=follow)
        self.addCleanup(view.deleteLater)
        vorher = {i.id for i in view._instances}
        self.addCleanup(lambda: [view._fm.remove(i.id)
                                 for i in list(view._instances)
                                 if i.id not in vorher])
        return view

    def test_die_efx_liste_benennt_den_kopf_auf_JEDEM_ihrer_drei_wege(self):
        """★★ Die EFX-Zielliste wird an DREI Stellen gefuellt (Auswahl folgen,
        automatisch zuweisen, von Hand hinzufuegen) und beim Laden noch einmal
        neu geschrieben. Jede Stelle braucht die Modellkarte — eine, die sie
        vergisst, faellt sonst nicht auf, weil eine andere kurz darauf
        drueberschreibt."""
        erwartet = f"Fixture #1 · {head_label_short(_PIXEL_MODELL, 3)}"

        # (a) Auswahl folgen. ``_sync_follow_selection`` steigt in einer
        # unsichtbaren View bewusst sofort aus (Wurzel-Fix 2026-06-24), gefahren
        # wird deshalb die Methode, an die es delegiert.
        folge = self._efx_view(follow=True)
        folge._add_efx()
        self.state.set_selected_cells(["1:3"])
        folge._assign_from_selection()
        self.assertEqual(self._efx_zeilen(folge), [erwartet])

        # (b) automatisch zuweisen — der Weg von „▶ Start" ohne Geraete
        auto = self._efx_view(follow=False)
        auto._add_efx()
        auto._current.fixtures.clear()
        auto._fx_list.clear()
        auto._auto_assign_if_empty(allow_all=True)
        self.assertEqual(self._efx_zeilen(auto), [erwartet])

        # (c) von Hand hinzufuegen — „+ Gerät"
        hand = self._efx_view(follow=False)
        hand._add_efx()
        hand._current.fixtures.clear()
        hand._fx_list.clear()
        hand._add_fixture()
        self.assertEqual(self._efx_zeilen(hand), [erwartet])

    def test_das_fan_werkzeug_erfindet_ohne_die_quelle_keinen_namen(self):
        """★ Das Fan-Werkzeug ist ohne ``app_state`` importierbar (Modulkopf).
        Fehlt die EINE Quelle, schreibt es KEINEN eigenen Kopfnamen hin — eine
        zweite Regel an dieser Stelle waere genau der Fehler, den FM-14b behebt.
        Die Zeile nennt dann nur noch das Geraet."""
        from src.ui.widgets import fan_tool
        from src.ui.widgets.fan_tool import FanTool
        w = FanTool()
        self.addCleanup(w.deleteLater)
        w.set_cells(["1:3"])
        self.assertEqual(w._table.item(0, 1).text(),
                         f"G1 · {head_label_short(_PIXEL_MODELL, 3)}")
        orig = fan_tool.head_label_short
        fan_tool.head_label_short = None
        self.addCleanup(lambda: setattr(fan_tool, "head_label_short", orig))
        w.set_cells(["1:3"])
        self.assertEqual(w._table.item(0, 1).text(), "G1")

    def test_die_command_line_nimmt_den_state_den_sie_bekommt(self):
        """Die Command-Line darf nicht am uebergebenen State vorbei nach dem
        globalen greifen: ein State ohne Geraete kennt kein Modell."""
        from src.core.cmdline.parser import _head_modelle
        import types
        self.assertEqual(_head_modelle(types.SimpleNamespace()), {})
        self.assertEqual(_head_modelle(self.state).get(1), _PIXEL_MODELL)


# ════════════════════════════════════════════════════════════════════════════
# 7. ★★ Kanalname statt Segmentname — wo der Kopf-Index KEIN Segment ist
# ════════════════════════════════════════════════════════════════════════════

class KanalnameStattSegmentnameTest(_RigFall):
    """★★ Ruege 1, an der Flaeche gemessen: „wer den ersten Pixel greift,
    greift ins Falsche".

    Der Kopf-Index gehoert dem ATTRIBUT, nicht dem Geraet: ``attr#N`` ist das
    N-te Vorkommen VON DIESEM Attribut. Am Robe Spiider im Pixelmodus sind die
    Segmente die 20 Farb-Baenke; die 21 Rohkanaele zaehlen davon voellig
    unabhaengig. Vor dieser Runde bekam trotzdem JEDER Pro-Kopf-Regler den
    Segmentnamen angehaengt::

        Pixel 1 gewaehlt -> „Grundfarbe Shutter · P1"  schreibt DMX  9 (Grundfarbe Rot Fein)
        Pixel 3 gewaehlt -> „Grundfarbe Shutter · P3"  schreibt DMX 13 (Grundfarbe Blau Fein)

    Der Name war doppelt falsch: der Kanalname stammte von der Vorlage, und das
    genannte Segment steuerte der Regler ueberhaupt nicht. Jetzt traegt so ein
    Regler den Namen des Kanals, den er WIRKLICH schreibt — gemessen ueber den
    echten Schreibweg (Slider bewegen, Programmer-Schluessel zurueckgelesen,
    Kanal ueber ``channel_occurrence_keys`` aufgeloest), nicht ueber die
    Funktion, die auch beschriftet."""

    def _channels(self, fixture):
        from src.core.app_state import get_channels_for_patched
        return get_channels_for_patched(fixture)

    def _regler_schreibt(self, fid: int, head: int) -> list:
        """``[(Reglerbeschriftung, Kanalname, DMX-Adresse)]`` — jeder Pro-Kopf-
        Regler EINZELN ueber den echten Weg gefahren."""
        from src.core.app_state import channel_occurrence_keys
        from src.ui.views.programmer_view import AttributeSlider
        view, _ = self._programmer_auf(fid, head)
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == fid)
        chans = self._channels(fx)
        regler = [w for w in view.findChildren(AttributeSlider)
                  if w._display_name and w._head == head
                  and all(getattr(f, "fid", None) == fid for f in w._fixtures)]
        self.assertTrue(regler, f"kein Pro-Kopf-Regler fuer {fid}:{head}")
        out = []
        for w in sorted(regler, key=lambda x: x._display_name):
            vorher = dict(self.state.programmer.get(fid, {}))
            w._slider.setValue(7 if w._slider.value() != 7 else 9)
            nachher = dict(self.state.programmer.get(fid, {}))
            geaendert = [k for k, v in nachher.items() if vorher.get(k) != v]
            self.assertEqual(len(geaendert), 1,
                             f"{w._display_name!r} schrieb {geaendert}")
            kanal = next((c for c, k in channel_occurrence_keys(chans)
                          if k == geaendert[0]), None)
            self.assertIsNotNone(kanal, f"{geaendert[0]!r} trifft keinen Kanal")
            out.append((w._display_name, kanal.name,
                        int(fx.address) + int(kanal.channel_number) - 1))
        return out

    def test_der_griff_der_frueher_danebenging(self):
        """★★ Genau der gemeldete Fall, mit Kanalnummer aus dem CHART (Spiider
        Mode 7: Kanal 9 = „Grundfarbe Rot Fein", Kanal 13 = „Grundfarbe Blau
        Fein") — nicht aus der Funktion, die auch schreibt."""
        self.assertEqual(self._regler_schreibt(1, 1),
                         [("Grundfarbe Rot Fein", "Grundfarbe Rot Fein", 9)])
        self.assertEqual(self._regler_schreibt(1, 3),
                         [("Grundfarbe Blau Fein", "Grundfarbe Blau Fein", 13)])

    def test_jeder_pro_kopf_regler_heisst_wie_sein_kanal(self):
        """Ueber die ganze Breite: die Grundfarbe (10 Regler) und beide Raender
        des Rings."""
        for head in (0, 1, 3, 19):
            with self.subTest(head=head):
                gemessen = self._regler_schreibt(1, head)
                self.assertTrue(gemessen)
                for name, kanal, dmx in gemessen:
                    self.assertEqual(name, kanal,
                                     f"Regler {name!r} schreibt DMX {dmx} "
                                     f"({kanal!r})")

    def test_kein_pro_kopf_regler_behauptet_ein_pixel(self):
        """Die Gegenrichtung: an einem Regler ohne Segment-Bezug darf KEIN
        Pixelname stehen — auch nicht der des gerade gewaehlten Kopfes."""
        pixelnamen = {head_label_for_model(_PIXEL_MODELL, n)
                      for n in range(1, 20)} | {
                      head_label_short(_PIXEL_MODELL, n) for n in range(1, 20)}
        for head in (0, 1, 3, 19):
            for name, _kanal, _dmx in self._regler_schreibt(1, head):
                for p in pixelnamen:
                    self.assertNotRegex(
                        name, rf"(?<![\w]){re.escape(p)}(?![\w])",
                        f"Regler {name!r} (Kopf {head}) nennt {p!r}")

    def test_ohne_aufloesbaren_kanal_bleibt_die_bestandsform(self):
        """POSITIVKONTROLLE der Rueckfallkante: laesst sich der Kanal nicht
        eindeutig aufloesen (hier: gar kein Geraet in der Hand), beschriftet der
        Regler weiter wie bisher — die Aenderung ist additiv, nicht ersetzend."""
        from src.core.app_state import head_channel_name
        from src.ui.views.programmer_view import ProgrammerView
        roh = next(c for c in self._channels(self.spiider)
                   if (c.attribute or "") == "raw")
        self.assertIsNone(head_channel_name([], "raw", 3))
        self.assertEqual(ProgrammerView._head_slider_name(roh, [], 3),
                         f"{roh.name} · {head_label_short('', 3)}")


# ════════════════════════════════════════════════════════════════════════════
# 8. ★★ Die Flaechen ohne Geraet — attr_label und ihre vier Aufrufer
# ════════════════════════════════════════════════════════════════════════════

class KontextfreieBeschriftungTest(_RigFall):
    """``attr_groups.attr_label`` hat kein Geraet in der Hand und uebersetzt
    ``color_r#3`` deshalb zu „Rot (Kopf 4)" — dasselbe Segment, das ueberall
    sonst „Pixel 3" heisst. WELCHES Segment ein ``#N`` meint, kann nur das
    GERAET sagen. Darum liegt die geraetebewusste Fassung
    (``app_state.attr_label_for``) dort, wo die Geraete sind, und ``attr_label``
    bleibt unveraendert die Fassung fuer Aufrufer ohne Geraet."""

    def test_ohne_geraet_bleibt_alles_wie_bisher(self):
        from src.core.app_state import attr_label_for
        from src.core.attr_groups import attr_label
        for a in ("color_r", "color_r#3", "tilt#1", "intensity", "color_r#x"):
            with self.subTest(attr=a):
                self.assertEqual(attr_label_for(a), attr_label(a))
                self.assertEqual(attr_label_for(a, [self.movbar]), attr_label(a))

    def test_am_pixel_kopf_heisst_das_segment_wie_ueberall(self):
        from src.core.app_state import attr_label_for
        for h in (0, 3, 19):
            with self.subTest(head=h):
                key = "color_r" if h == 0 else f"color_r#{h}"
                self.assertEqual(
                    attr_label_for(key, [self.spiider]),
                    f"Rot ({head_label_for_model(_PIXEL_MODELL, h)})")

    def test_ein_attribut_ohne_segment_bleibt_beim_index(self):
        """★ ``tilt#1`` ist am Pixel-Kopf der zweite TILT-Kanal, nicht Pixel 1.
        Ein Pixelname waere dort der Name eines anderen Dings."""
        from src.core.app_state import attr_head_is_segment, attr_label_for
        from src.core.attr_groups import attr_label
        for a in ("tilt#1", "raw#3", "shutter#2", "intensity#1"):
            with self.subTest(attr=a):
                self.assertFalse(attr_head_is_segment(_PIXEL_MODELL, a))
                self.assertEqual(attr_label_for(a, [self.spiider]), attr_label(a))
        for a in ("color_r#3", "color_g", "color_w#2"):
            self.assertTrue(attr_head_is_segment(_PIXEL_MODELL, a))
        # POSITIVKONTROLLE: an jedem anderen Modell zaehlen ALLE Attribute ueber
        # denselben Kopf — sonst wuerde die Regel ringlose Geraete umbauen.
        for a in ("tilt#1", "raw#3", "color_r#3"):
            self.assertTrue(attr_head_is_segment("", a))

    def test_gemischte_geraete_benennen_kein_segment(self):
        from src.core.app_state import attr_label_for
        from src.core.attr_groups import attr_label
        for paar in ([self.spiider, self.movbar], [self.movbar, self.spiider]):
            self.assertEqual(attr_label_for("color_r#3", paar),
                             attr_label("color_r#3"))

    def test_der_kanalname_wird_nur_bei_EINIGKEIT_uebernommen(self):
        """``head_channel_name`` darf nicht „irgendeinen" Namen nehmen: Kopf 3
        heisst am Spiider „P3 Rot" und an der Mover-Bar „Kopf 4 Rot"."""
        from src.core.app_state import head_channel_name
        self.assertEqual(head_channel_name([self.spiider], "color_r", 3), "P3 Rot")
        self.assertEqual(head_channel_name([self.movbar], "color_r", 3),
                         "Kopf 4 Rot")
        self.assertIsNone(head_channel_name([self.spiider, self.movbar],
                                            "color_r", 3))
        self.assertIsNone(head_channel_name([self.movbar], "raw", 3),
                          "die Mover-Bar hat gar keinen Rohkanal")

    def test_der_speichern_dialog_fragt_die_geraete_die_den_kanal_liefern(self):
        """★★ Ein Snap umfasst mehrere Geraete. Wer die Beschriftung ueber ALLE
        Geraete des Scopes bildet statt ueber die, die diesen Kanal wirklich
        liefern, faellt still auf den Index zurueck — obwohl nur EIN Geraet den
        Kanal ueberhaupt hat."""
        from src.ui.views.snap_file_panel import ChannelSelectDialog
        nur_pixel = ChannelSelectDialog({1: {"color_r#3": 200}, 2: {"pan": 10}})
        self.addCleanup(nur_pixel.deleteLater)
        self.assertEqual(nur_pixel._attr_checks["color_r#3"].text(),
                         f"Rot ({head_label_for_model(_PIXEL_MODELL, 3)})  (1)")
        # Liefern ihn BEIDE, benennt er kein einzelnes Segment mehr.
        beide = ChannelSelectDialog({1: {"color_r#3": 200}, 2: {"color_r#3": 10}})
        self.addCleanup(beide.deleteLater)
        self.assertEqual(beide._attr_checks["color_r#3"].text(),
                         "Rot (Kopf 4)  (2)")

    def test_mapping_ziele_tragen_nie_einen_kopf_schluessel(self):
        """★ Warum ``mapped_channel_editor`` unveraendert bleibt: seine Ziele
        kommen direkt aus der Kanal-Liste und tragen nie ein ``#N`` — dort gibt
        es gar keinen Kopf zu benennen. Am echten Ziel-Auswahlfeld gemessen,
        mit dem Pixel-Kopf in der Auswahl."""
        from src.ui.widgets.mapped_channel_editor import MappedChannelEditor
        self.state.set_selected_fids([1])
        ed = MappedChannelEditor()
        self.addCleanup(ed.deleteLater)
        ed._on_selection()
        ziele = [ed._target_combo.itemData(i)
                 for i in range(ed._target_combo.count())]
        self.assertTrue(ziele, "keine Ziele — der Test misst nichts")
        self.assertEqual([z for z in ziele if "#" in str(z)], [])

    def test_laser_regler_tragen_nie_einen_kopf_schluessel(self):
        """Dasselbe fuer ``laser_view``: eine Regler-Zeile bekommt einen KANAL,
        und ein Kanal-Attribut traegt nie ein ``#N``. Am echten Widget mit dem
        echten Profil gemessen — der Party-Laser hat sogar ZWEI ``color_r``."""
        from PySide6.QtWidgets import QLabel
        from src.core.app_state import get_channels_for_patched
        from src.ui.views.laser_view import _ChannelRow
        laser = self._patch("PARTYLASER", "7-Kanal", 7, fid=7, adresse=700)
        chans = get_channels_for_patched(laser)
        self.assertEqual(sum(1 for c in chans if c.attribute == "color_r"), 2,
                         "ohne wiederholtes Attribut misst der Test nichts")
        for ch in chans:
            self.assertNotIn("#", ch.attribute or "")
            row = _ChannelRow(ch, lambda *a: None)
            self.addCleanup(row.deleteLater)
            self.assertNotIn("Kopf", row.findChild(QLabel).text())

    def test_die_command_line_nennt_die_vorhandenen_koepfe_beim_namen(self):
        """★ Die Fehlermeldung nannte die vorhandenen Koepfe „(K1–K20)" — 20
        Segmente mit einem zweiten Namen. Die zu gross getippte Nummer bleibt
        bewusst in der getippten Zaehlung: sie beschreibt die EINGABE und
        benennt kein vorhandenes Segment."""
        from src.core.cmdline.parser import parse
        res = parse("1:21 red 255").execute(self.state)
        self.assertFalse(res.ok)
        spanne = (f"({head_label_short(_PIXEL_MODELL, 0)}–"
                  f"{head_label_short(_PIXEL_MODELL, 19)})")
        self.assertIn(spanne, res.message)
        self.assertNotIn("K1–K20", res.message)
        # Und die getippte Nummer ist mit keinem Segmentnamen verwechselbar:
        # am Pixel-Kopf heisst kein einziges Segment „K…".
        self.assertIn("K21", res.message)
        self.assertNotIn("K21", {head_label_short(_PIXEL_MODELL, n)
                                 for n in range(0, 30)})


if __name__ == "__main__":
    unittest.main()
