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

    def _programmer(self, fid: int, head: int) -> dict:
        """Geraeteliste, Kopfzeile und Regler des Programmers — gebaut vom
        echten ``_refresh_fixture_list`` und der echten Auswahl-Naht."""
        from src.ui.views.programmer_view import ProgrammerView, AttributeSlider
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
        regler = sorted({w._display_name for w in view.findChildren(AttributeSlider)
                         if w._display_name and w._head == head
                         and all(getattr(f, "fid", None) == fid
                                 for f in w._fixtures)})
        self.assertTrue(regler, f"kein Kopf-Regler fuer {zelle}")
        return {"Programmer-Geraeteliste": treffer.text().strip(),
                "Programmer-Kopfzeile": view._lbl_selection.text(),
                "Programmer-Regler": regler[0]}

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
        out = {}
        for teil in (self._programmer(fid, head), self._raster(fid, head),
                     self._matrix(fid, head), self._efx(fid, head),
                     self._fan(fid, head), self._cmdline(fid, head)):
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
        # 9 Flaechen; die Grundfarbe hat bewusst KEINE Rasterzelle und damit
        # auch keinen Matrix-Tooltip (FM-14b) — sonst zoege jeder Effekt sie mit.
        self.assertEqual(len(flaechen), 8 if head == 0 else 9, sorted(flaechen))
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
            # Der Kanalname stammt aus dem Profil (Vorlage = erstes Vorkommen),
            # nur das „· K4" dahinter ist die Kopf-Beschriftung.
            "Programmer-Regler": "Kopf 1 Pan · K4",
            "Gruppen-Rasterzelle": "2·K4",
            "Gruppen-Raster-Tooltip": "G2 · Kopf 4",
            "Matrix-Vorschau-Tooltip": "G2 · Kopf 4",
            "EFX-Zielliste": "Fixture #2 · K4  offset=0.00",
            "Fan-Werkzeug": "G2 · K4",
            "Command-Line-Statuszeile": "Selektiert: 1 (2·K4)",
        })

    def test_auch_der_erste_kopf_bleibt_kopf_1(self):
        """Kopf 0 heisst hier weiter „Kopf 1" — die Grundfarben-Regel darf NICHT
        auf gewoehnliche Mehrkopf-Geraete ausschlagen."""
        flaechen = self.alle_flaechen(2, 0)
        self.assertEqual(flaechen["Programmer-Geraeteliste"], "└ Kopf 1")
        self.assertEqual(flaechen["Gruppen-Rasterzelle"], "2·K1")
        self.assertEqual(flaechen["Command-Line-Statuszeile"],
                         "Selektiert: 1 (2·K1)")
        for text in flaechen.values():
            self.assertNotIn("Grundfarbe", text)
            self.assertNotIn("Pixel", text)


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

    def test_die_bar_regler_eines_pixel_doppeltilters_folgen_der_quelle(self):
        """★ Der zweite ``· K{n+1}``-Regler im Programmer. Ein Doppeltilter mit
        ausdruecklich gesetztem ``viz_model = 'pixel_head'`` (Fixture-Generator)
        muss auch hier heissen wie in der Geraeteliste. Der Kanalname davor
        kommt unveraendert aus dem Profil."""
        self.assertEqual(
            self._tilt_regler(pixel=True),
            [f"Tilt Bar Links · {head_label_short(_PIXEL_MODELL, 0)}",
             f"Tilt Bar Rechts · {head_label_short(_PIXEL_MODELL, 1)}"])

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


if __name__ == "__main__":
    unittest.main()
