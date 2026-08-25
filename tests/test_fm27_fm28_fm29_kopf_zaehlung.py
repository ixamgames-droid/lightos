"""FM-27/28/29 — die Pro-Kopf-Regler zaehlten VORKOMMEN statt KOEPFE.

Drei Befunde, eine Ursache: ``attr_head_count_for_channels`` beantwortete „wie
viele Koepfe hat dieses Geraet fuer dieses Attribut" mit der Zahl der Kanaele,
die das Attribut tragen. Aus dieser Zahl baut ``_slider_head_buckets`` die
Regler des Programmers — jeder Zaehlfehler wird dort ein Regler zu viel, ein
Geraet zu viel oder ein Regler an der falschen Achse.

==========  ====================================  =========================  ===============
Befund      Geraet (echtes Library-Profil)        Antwort VORHER             richtig
==========  ====================================  =========================  ===============
**FM-29**   ``HYDRABEAM 4000 RGBW [19-Kanal]``    ``intensity`` -> **5**     4
**FM-27**   ``MOVBAR4 [22-Kanal]``                ``speed`` -> **1**         0
**FM-28**   ``Robin Spiider [91-Kanal Pixel]``    ``raw`` -> **21**          1
==========  ====================================  =========================  ===============

Was daraus in der Oberflaeche wurde, ist am gebauten Regler gemessen:

* **FM-29** Die 5 Intensity-Kanaele der Hydrabeam sind ``CH1 Master Dimmer`` +
  ``CH9/12/15/18 Kopf 1..4 Dimmer``. Die Gruppen-Zelle ``1:4`` (Kopf-Index 4)
  erzeugte damit einen Regler „Kopf 4 Dimmer · **K5**" — und der schrieb ueber
  ``intensity#4`` auf **denselben** CH18 wie der danebenstehende „· K4".
  **Zwei Regler auf einem Kanal**, einer davon falsch beschriftet: wer K4
  hochzieht und danach K5, sieht seinen ersten Zug ueberschrieben.
* **FM-27** Ein Attribut, das ein Geraet gar nicht hat, galt als „hat Kopf 1".
  Der ``speed``-Regler von Kopf 1 trieb damit ``MOVBAR4`` mit, obwohl die
  keinen ``speed``-Kanal hat: der Wert landete im Programmer-Dict und
  **nirgends** auf DMX. Dieselbe stille Klasse wie FM-9/A5. Betrifft auch den
  geraeteweiten Regler, denn die Vorlage ist die UNION der Auswahl.
* **FM-28** ``raw`` ist kein Attribut, sondern der Auffangkorb fuer unerkannte
  Kanaele — am Spiider tragen 21 voellig verschiedene Funktionen dieses
  Attribut. „Kopf 3" landete darueber auf ``raw#2`` = CH11 „Grundfarbe Grün
  Fein".

★ **Gemessen wird gegen die echten Profile der Geraetebibliothek** (Builtins
ueber ihren KURZnamen — der Anzeigename existiert je nach Rechner nur lokal,
Fallenklasse QA-23), nicht gegen selbstgebaute Attrappen: sonst prueft der Test
seine eigene Nachbildung der Kanalliste.

★★ Und gemessen wird am **Ausgang**: welcher DMX-Kanal traegt nach einem Zug am
Regler welchen Wert. „Der Dict-Eintrag fehlt" waere kein Nachweis — genau das
Fehlen einer DMX-Wirkung ist ja der Befund.

Positivkontrolle: ``HYDRABEAM 4000 RGBW [56-Kanal]`` ist ein echter Multi-Head
mit sauberer Kopf-Karte (4 Pan/Tilt, 4 Intensity, 4 Shutter, je Kopf einer, kein
geteilter Master) und ``MOVBAR4`` einer mit 4 Pan/Tilt/RGB. Beide muessen sich
byte-genau wie vorher verhalten — sonst waere der Fix ein Waechter, der alles
beanstandet.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import (attr_has_head_axis,                 # noqa: E402
                                attr_head_count_for_channels,
                                get_channels_for_patched, get_state)
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureMode, FixtureProfile,  # noqa: E402
                                      PatchedFixture)
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views.programmer_view import (AttributeSlider,          # noqa: E402
                                          ProgrammerView)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    """Profil-ID ueber den KURZnamen eines Builtins (nie ueber den Anzeigenamen —
    der existiert je nach Rechner nur lokal, Fallenklasse QA-23)."""
    with Session(fdb_engine()) as s:
        got = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()
    assert got is not None, f"Builtin-Profil {short} fehlt in der Bibliothek"
    return int(got)


def _mode_name(short: str, channels: int) -> str:
    """Modusname ueber die KANALZAHL — die Anzeigenamen der Modi sind Fliesstext
    („19-Kanal 4×Move + RGBW"), und dieser Test darf nicht an ihrer Schreibweise
    haengen."""
    with Session(fdb_engine()) as s:
        return s.execute(select(FixtureMode.name).where(
            FixtureMode.fixture_id == _pid(short),
            FixtureMode.channel_count == channels)).scalars().first()


class _Basis(unittest.TestCase):
    """Gemeinsamer Unterbau: echte Profile patchen, echte View bauen, DMX lesen."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self._addr = 1

    # ── Patchen ───────────────────────────────────────────────────────────
    def _patch(self, fid: int, short: str, channels: int,
               ftype: str = "moving_head") -> PatchedFixture:
        mode = _mode_name(short, channels)
        self.assertIsNotNone(
            mode, f"Builtin {short} hat keinen {channels}-Kanal-Modus — der "
                  f"Test wuerde sonst ein anderes Geraet messen als er behauptet")
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"F{fid}", fixture_profile_id=_pid(short),
            mode_name=mode, universe=1, address=self._addr,
            channel_count=channels, fixture_type=ftype), undoable=False)
        self._addr += channels
        return self._fx(fid)

    def _fx(self, fid: int) -> PatchedFixture:
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _kopfzahl(self, fid: int, attr: str) -> int:
        fx = self._fx(fid)
        return int(attr_head_count_for_channels(
            fx, get_channels_for_patched(fx), attr))

    # ── Regler ────────────────────────────────────────────────────────────
    def _slider_objs(self, cells) -> list:
        """Die gebauten ``AttributeSlider`` einer Auswahl — der ECHTE Bauweg
        (View + ``set_selected_cells``), nicht ein direkter Aufruf der
        Bucket-Funktion. Frische View je Messung, sonst liefert
        ``findChildren`` auch die Regler frueherer Auswahlen."""
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_cells(list(cells))
        _app().processEvents()
        return v.findChildren(AttributeSlider)

    def _regler(self, cells, attr: str) -> list:
        """``(kopf, fids, slider)`` je Regler dieses Attributs."""
        return [(s._head, tuple(f.fid for f in s._fixtures), s)
                for s in self._slider_objs(cells)
                if s._channel.attribute == attr]

    # ── DMX ───────────────────────────────────────────────────────────────
    def _grundstellung(self, *fids: int):
        """Einmal spuelen, damit die ``default_value`` der Kanaele schon auf DMX
        stehen.

        ★ Ohne das enthielte der ERSTE gemessene Zug zusaetzlich den
        Erst-Flush (Pan/Tilt springen von 0 auf ihren Default 128) — die
        Vorher/Nachher-Differenz waere dann nicht die Wirkung des Reglers."""
        for fid in fids:
            self.state._flush_programmer_to_dmx(int(fid))

    def _dmx(self, fid: int) -> dict:
        """``{Kanalname: DMX-Wert}`` dieses Geraets — das, was auf der Buehne
        ankommt."""
        fx = self._fx(fid)
        uni = self.state.universes[fx.universe]
        return {c.name: uni.get_channel(fx.address + c.channel_number - 1)
                for c in get_channels_for_patched(fx)}

    def _zieh(self, slider, fid: int, wert: int) -> dict:
        """Am Regler ziehen (genau der Weg des Nutzers:
        ``AttributeSlider._apply_value`` -> ``set_programmer_value(head=…)``)
        und zurueckgeben, WELCHE Kanaele dieses Geraets sich dadurch geaendert
        haben: ``{Kanalname: neuer Wert}``."""
        self._grundstellung(fid)      # Erst-Flush nicht als Wirkung zaehlen
        vorher = self._dmx(fid)
        slider._apply_value(fid, wert)
        nachher = self._dmx(fid)
        return {k: v for k, v in nachher.items() if vorher.get(k) != v}


class KopfzahlGegenDieBibliothekTest(_Basis):
    """Die Zaehlung selbst — an echten Profilen, nicht an Attrappen."""

    def test_fm29_geteilter_master_ist_kein_fuenfter_kopf(self):
        """``HYDRABEAM 4000 RGBW [19-Kanal]``: CH1 Master + CH9/12/15/18 je Kopf.
        Fuenf Kanaele, **vier** Koepfe — und die Bewegungsachse desselben
        Geraets sagt dasselbe."""
        self._patch(1, "HYDRA4000", 19)
        self.assertEqual(self._kopfzahl(1, "intensity"), 4)
        self.assertEqual(self._kopfzahl(1, "pan"), 4,
                         "die Anker-Achse ist die Gegenprobe zur Kopfzahl")
        self.assertEqual(self._kopfzahl(1, "color_r"), 1,
                         "EINE gemeinsame RGBW-Bank — daran aendert FM-29 nichts")

    def test_fm27_fehlendes_attribut_ist_null_koepfe(self):
        """``MOVBAR4 [22-Kanal]`` hat pan/tilt/RGB je Kopf, aber KEINEN
        ``speed``-Kanal. ``1`` hiess „hat Kopf 1" und liess das Geraet im
        Regler stehen."""
        self._patch(1, "MOVBAR4", 22)
        self.assertNotIn("speed", {(c.attribute or "") for c
                                   in get_channels_for_patched(self._fx(1))},
                         "das Profil muss diesen Kanal wirklich nicht haben")
        self.assertEqual(self._kopfzahl(1, "speed"), 0)
        self.assertEqual(self._kopfzahl(1, "gobo_wheel"), 0)
        self.assertEqual(self._kopfzahl(1, "pan"), 4,
                         "was das Geraet HAT, wird unveraendert gezaehlt")

    def test_fm28_raw_ist_geraeteweit(self):
        """``Robin Spiider [91-Kanal Pixel]``: 21 verschiedene Funktionen tragen
        ``raw``. Aus 21 Vorkommen 21 „Koepfe" zu machen ist eine Zahl ohne
        Bedeutung."""
        self._patch(1, "SPIIDER", 91)
        roh = [c for c in get_channels_for_patched(self._fx(1))
               if (c.attribute or "") == "raw"]
        self.assertGreater(len(roh), 2,
                           "das Profil muss wirklich mehrere raw-Kanaele haben")
        self.assertGreater(
            len({c.name for c in roh}), 2,
            "und sie muessen verschiedene Funktionen sein — sonst waere die "
            "Vorkommens-Zaehlung gar nicht falsch")
        self.assertEqual(self._kopfzahl(1, "raw"), 1)
        self.assertFalse(attr_has_head_axis("raw"))
        self.assertTrue(attr_has_head_axis("intensity"))

    def test_positivkontrolle_saubere_kopf_karte_bleibt(self):
        """★ Der Gegenfall: ``HYDRABEAM [56-Kanal]`` hat je Kopf einen eigenen
        Dimmer/Shutter/Speed und KEINEN geteilten Master. Dort waren die
        Vorkommen schon immer die Koepfe — die Antwort darf sich nicht
        aendern."""
        self._patch(1, "HYDRA4000", 56)
        for attr in ("intensity", "shutter", "speed", "pan", "tilt", "color_r"):
            self.assertEqual(self._kopfzahl(1, attr), 4,
                             f"{attr} an der 56-Kanal-Hydrabeam")


class FM29ZweiReglerAufEinemKanalTest(_Basis):
    """Der gemeldete Ausgang: die Gruppen-Zelle ``1:4`` baute einen fuenften
    Dimmer-Regler, der auf den Kanal des vierten schrieb."""

    def _dimmer_regler(self, cells) -> dict:
        return {kopf: (fids, s) for kopf, fids, s
                in self._regler(cells, "intensity") if kopf is not None}

    def test_kein_k5_regler_mehr(self):
        self._patch(1, "HYDRA4000", 19)
        koepfe = sorted(self._dimmer_regler(["1:3", "1:4"]))
        self.assertEqual(koepfe, [3],
                         "Kopf-Index 4 gibt es an diesem Geraet nicht — es hat "
                         "vier Koepfe und einen geteilten Master")

    def test_kein_zweiter_regler_auf_ch18(self):
        """★★ Der eigentliche Schaden, am DMX-Kanal gemessen: zwei Regler, die
        denselben Kanal schreiben, ueberschreiben einander stumm.

        Gemessen wird, welche Kanaele ein Zug am Regler VERAENDERT — nicht ein
        Dict-Eintrag."""
        self._patch(1, "HYDRA4000", 19)
        regler = self._dimmer_regler(["1:3", "1:4"])
        ziele = {}
        for kopf, (_fids, s) in sorted(regler.items()):
            geaendert = self._zieh(s, 1, 60 + kopf)
            self.assertTrue(geaendert,
                            f"der Regler K{kopf + 1} bewegt gar keinen Kanal")
            ziele[kopf] = geaendert
        kopf_kanaele = [set(g) - {"Master Dimmer"} for g in ziele.values()]
        for i, a in enumerate(kopf_kanaele):
            for b in kopf_kanaele[i + 1:]:
                self.assertEqual(a & b, set(),
                                 f"zwei Kopf-Regler schreiben auf {a & b}")
        self.assertEqual(ziele[3].get("Kopf 4 Dimmer"), 63,
                         "K4 muss weiterhin CH18 treffen")

    def test_zelle_1_4_bleibt_bedienbar(self):
        """★ Kein Regler zu viel heisst nicht „kein Regler": waehlt man NUR die
        Zelle ``1:4``, gibt es fuer dieses Geraet keinen vierten Kopf-Index —
        der Dimmer faellt dann auf den geraeteweiten Regler zurueck statt zu
        verschwinden (dieselbe Regel wie bei der geteilten Farbe, FM-18)."""
        self._patch(1, "HYDRA4000", 19)
        regler = self._regler(["1:4"], "intensity")
        self.assertTrue(regler, "der Dimmer ist ganz verschwunden")
        self.assertEqual({kopf for kopf, _f, _s in regler}, {None})


class FM27WertKommtNichtAufDmxAnTest(_Basis):
    """Ein Geraet ohne den Kanal steckte im Regler — und bekam einen Wert, den
    kein DMX-Kanal je sah."""

    def test_kopf_regler_treibt_nur_geraete_mit_dem_kanal(self):
        """``MOVBAR4`` (kein ``speed``) + ``HYDRABEAM 19ch`` (CH19 „Head
        Speed"), Kopf 1 auf beiden.

        ★ Der Nachweis laeuft ueber den Ausgang: fuer JEDES Geraet, das der
        Regler treibt, muss ein Zug am Regler mindestens einen DMX-Kanal dieses
        Geraets bewegen."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(2, "HYDRA4000", 19)
        regler = [(fids, s) for kopf, fids, s
                  in self._regler(["1:0", "2:0"], "speed") if kopf == 0]
        self.assertEqual(len(regler), 1, "genau ein Kopf-1-Speed-Regler erwartet")
        fids, s = regler[0]
        # ★ Zuerst der Ausgang, dann die Besitzerliste: die Zusage lautet „der
        # Wert kommt an", nicht „das Tupel sieht richtig aus".
        for fid in fids:
            self.assertTrue(
                self._zieh(s, fid, 177),
                f"der Regler treibt Geraet {fid}, aber der Wert bewegt dort "
                f"keinen einzigen DMX-Kanal — genau der stille Fehler aus FM-27")
        self.assertEqual(fids, (2,),
                         "die MOVBAR4 hat keinen speed-Kanal und darf in diesem "
                         "Regler nicht mehr stecken")

    def test_movbar4_bleibt_wirkungslos_wenn_man_es_doch_versucht(self):
        """★ Die Gegenprobe zur Messmethode: schreibt man ``speed`` VON HAND auf
        die MOVBAR4, bewegt sich nichts. Ohne diesen Nachweis koennte
        ``_zieh`` auch dann leer sein, wenn die Messung selbst nicht greift."""
        self._patch(1, "MOVBAR4", 22)
        self._grundstellung(1)
        vorher = self._dmx(1)
        self.state.set_programmer_value(1, "speed", 177, undoable=False)
        self.assertEqual(self._dmx(1), vorher,
                         "ein speed-Wert auf einem Geraet ohne speed-Kanal ist "
                         "stumm — das ist die Fehlerklasse, nicht der Messfehler")

    def test_auch_der_rueckfall_auf_geraeteweit_laesst_es_heraus(self):
        """★ Der dritte Weg in denselben Regler: hat KEIN Geraet den gewaehlten
        Kopf fuer dieses Attribut, faellt der Regler auf geraeteweit zurueck
        (FM-18, damit das Attribut bedienbar bleibt). Auch dieser Rueckfall darf
        nur Geraete aufnehmen, die den Kanal haben.

        Gemessen an Kopf 4 von ``MOVBAR4`` (kein ``focus``) + Kopf 4 des
        ``SHARPY [16-Kanal]`` (EIN ``focus``-Kanal, also gar kein vierter Kopf
        dafuer). ``focus`` bewusst statt ``speed``: fuer ``speed`` baut die
        Schnellwahl einen zweiten, eigenen Regler („Pan/Tilt-Speed"), der diesen
        Bauweg gar nicht benutzt — der Test wuerde dann zwei Regler zaehlen und
        die Kante verfehlen."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(2, "SHARPY", 16)
        self.assertEqual(self._kopfzahl(1, "focus"), 0)
        self.assertEqual(self._kopfzahl(2, "focus"), 1,
                         "ein einzelner Kanal — Kopf 4 gibt es dafuer nicht")
        regler = self._regler(["1:3", "2:3"], "focus")
        self.assertEqual([k for k, _f, _s in regler], [None],
                         "genau ein geraeteweiter Rueckfall-Regler erwartet")
        _kopf, fids, s = regler[0]
        for fid in fids:
            self.assertTrue(
                self._zieh(s, fid, 88),
                f"der Rueckfall-Regler treibt Geraet {fid}, bewegt dort aber "
                f"keinen DMX-Kanal")
        self.assertEqual(fids, (2,))

    def test_auch_der_geraeteweite_regler_laesst_es_heraus(self):
        """Die Vorlage ist die UNION der Auswahl: ``focus`` gibt es nur am
        ``SHARPY [16-Kanal]`` (CH9 „Fokus"), nicht an der ``MOVBAR4``. Ohne
        Kopf-Auswahl entstand trotzdem EIN Regler fuer beide."""
        self._patch(1, "SHARPY", 16)
        self._patch(2, "MOVBAR4", 22)
        self.assertEqual(self._kopfzahl(2, "focus"), 0)
        regler = self._regler(["1", "2"], "focus")
        self.assertTrue(regler, "der Fokus-Regler des Sharpy muss bleiben")
        for kopf, fids, s in regler:
            self.assertEqual(kopf, None, "ohne Kopf-Auswahl bleibt alles geraeteweit")
            for fid in fids:
                self.assertTrue(
                    self._zieh(s, fid, 44),
                    f"der Regler treibt Geraet {fid}, aber dort bewegt sich "
                    f"kein DMX-Kanal")
            self.assertEqual(fids, (1,),
                             "die MOVBAR4 hat keinen Fokus-Kanal")


class FM28RawBekommtKeinenKopfReglerTest(_Basis):
    """``raw`` ist der Auffangkorb, keine Kopf-Achse."""

    def test_kein_pro_kopf_raw_regler(self):
        self._patch(1, "SPIIDER", 91)
        for zelle in ("1:0", "1:2", "1:10", "1:19"):
            koepfe = [kopf for kopf, _f, _s in self._regler([zelle], "raw")]
            self.assertEqual(
                [k for k in koepfe if k is not None], [],
                f"{zelle}: fuer ``raw`` darf kein Pro-Kopf-Regler entstehen")
            self.assertIn(None, koepfe,
                          f"{zelle}: der geraeteweite raw-Regler muss bleiben — "
                          f"sonst waeren die unerkannten Kanaele unbedienbar")

    def test_der_geraeteweite_raw_regler_wirkt_wirklich(self):
        """★ Nicht nur „ist da": er muss auch ankommen — sonst haette FM-28 den
        Regler nur wirkungslos gemacht.

        Getroffen wird der Vorlagen-Kanal, und mit ihm **alle** ``raw``-Kanaele:
        ein geraeteweiter Wert auf dem Basis-Schluessel wird im DMX-Flush auf
        jedes Vorkommen gespiegelt, das nichts Eigenes hat. Das ist der
        Bestandsvertrag fuer geteilte Kanaele und aelter als FM-28 — hier steht
        er nur ausdruecklich da, damit die Reichweite nicht unbemerkt waechst.
        Kein Kanal AUSSERHALB von ``raw`` darf sich bewegen."""
        self._patch(1, "SPIIDER", 91)
        regler = [(fids, s) for kopf, fids, s
                  in self._regler(["1:2"], "raw") if kopf is None]
        self.assertEqual(len(regler), 1)
        fids, s = regler[0]
        self.assertEqual(fids, (1,))
        geaendert = self._zieh(s, 1, 91)
        self.assertIn(s._channel.name, geaendert,
                      "der Vorlagen-Kanal muss den Wert bekommen")
        roh = {c.name for c in get_channels_for_patched(self._fx(1))
               if (c.attribute or "") == "raw"}
        self.assertEqual(set(geaendert) - roh, set(),
                         "ein raw-Regler darf nichts ausserhalb von raw bewegen")
        self.assertEqual(set(geaendert.values()), {91})

    def test_die_farb_koepfe_des_spiiders_bleiben(self):
        """★ Positivkontrolle am selben Geraet: der Spiider hat 20 echte
        Farb-Ringe. FM-28 darf nur ``raw`` treffen, nicht die Farbe."""
        self._patch(1, "SPIIDER", 91)
        for zelle, kopf in (("1:0", 0), ("1:2", 2), ("1:19", 19)):
            rot = [k for k, _f, _s in self._regler([zelle], "color_r")]
            self.assertIn(kopf, rot,
                          f"{zelle}: der Rot-Regler dieses Rings fehlt")


class PositivkontrolleSauberesMultiHeadTest(_Basis):
    """★★ Ein Waechter, der alles beanstandet, ist so nutzlos wie einer, der
    nichts findet. Zwei echte Multi-Heads mit sauberer 1:1-Zuordnung muessen
    sich unveraendert verhalten."""

    def test_hydrabeam_56ch_jeder_kopf_schreibt_seinen_dimmer(self):
        """4 Koepfe, je ein eigener Dimmer, KEIN geteilter Master — genau der
        Fall, den FM-29 nicht anfassen darf."""
        self._patch(1, "HYDRA4000", 56)
        getroffen = {}
        for kopf in range(4):
            regler = [s for k, _f, s in self._regler([f"1:{kopf}"], "intensity")
                      if k == kopf]
            self.assertEqual(len(regler), 1,
                             f"Kopf {kopf + 1} hat keinen eigenen Dimmer-Regler")
            geaendert = self._zieh(regler[0], 1, 100 + kopf)
            self.assertEqual(list(geaendert), [f"Kopf {kopf + 1} Dimmer"],
                             f"Kopf {kopf + 1} bewegt {list(geaendert)}")
            getroffen[kopf] = geaendert
        self.assertEqual(len(getroffen), 4)

    def test_hydrabeam_56ch_kein_fuenfter_kopf(self):
        self._patch(1, "HYDRA4000", 56)
        self.assertEqual(
            [k for k, _f, _s in self._regler(["1:4"], "intensity")], [None],
            "auch hier gibt es keinen fuenften Kopf — der Regler faellt auf "
            "geraeteweit zurueck")

    def test_movbar4_pan_pro_kopf_unveraendert(self):
        """4 Pan-Kanaele, 4 Koepfe, kein geteilter Master: jeder Kopf-Regler
        schreibt genau seinen Pan-Kanal."""
        self._patch(1, "MOVBAR4", 22)
        for kopf in range(4):
            regler = [s for k, _f, s in self._regler([f"1:{kopf}"], "pan")
                      if k == kopf]
            self.assertEqual(len(regler), 1)
            geaendert = self._zieh(regler[0], 1, 30 + kopf)
            self.assertEqual(list(geaendert), [f"Kopf {kopf + 1} Pan"])

    def test_einkopf_geraet_bleibt_geraeteweit(self):
        """Die Mehrheit der Geraete: ein gewoehnlicher Moving Head darf gar
        keine Kopf-Regler bekommen — und keiner seiner Regler darf durch FM-27
        wegfallen."""
        self._patch(1, "SHARPY", 16)
        for attr in ("intensity", "speed", "focus", "pan", "prism"):
            regler = self._regler(["1"], attr)
            self.assertTrue(regler, f"{attr}: Regler fehlt")
            for kopf, fids, _s in regler:
                self.assertIsNone(kopf, f"{attr} wurde an Kopf {kopf} gebunden")
                self.assertEqual(fids, (1,))

    def test_mehrkopf_ohne_kopf_auswahl_unveraendert(self):
        """Ganzes Geraet gewaehlt = Bestandsfall: alles geraeteweit."""
        self._patch(1, "HYDRA4000", 19)
        for attr in ("intensity", "pan", "color_r", "shutter", "speed"):
            koepfe = {k for k, _f, _s in self._regler(["1"], attr)}
            self.assertEqual(koepfe, {None}, f"{attr}: {koepfe}")


# ═══════════════════════════════════════════════════════════════════════════
# Gegenpruefung zu #663 — die Regler, die NICHT aus _slider_head_buckets kommen
# ═══════════════════════════════════════════════════════════════════════════

class ReglerAusserhalbDesBucketWegsTest(_Basis):
    """★★ ``_slider_head_buckets`` ist **nicht der einzige** Bauweg fuer Regler.

    Der Gegenprueferbericht zu PR #663 hat das an zwei Stellen belegt, beide mit
    demselben Muster: die Vorlage (``_template_channels`` bzw.
    ``_color_template_channels``) ist die UNION der Attribute der Auswahl, also
    steht ein Regler auch dann da, wenn ihn nur EIN Geraet hat — und diese
    beiden Wege reichten ``fixtures`` unveraendert weiter:

    * ``_add_quick_select`` (Position-Tab) baut den mit „Pan/Tilt-Speed:"
      beschrifteten ``speed``-Regler selbst. Genau ``speed`` ist das
      Beispiel-Attribut von FM-27 — der Fix ging bis dahin an dem Regler vorbei,
      den der Nutzer dafuer wirklich anfasst.
    * ``_add_sync_color_sliders`` (Color-Tab) baut die Grundfarben-Regler.

    Gemessen wird deshalb **ueber alle** gebauten Regler eines Attributs, egal
    welcher Bauweg sie erzeugt hat, und am **Ausgang**: welcher DMX-Kanal
    bewegt sich, wenn man den Regler zieht.
    """

    def _zieh_am_regler(self, slider, fids, wert: int) -> dict:
        """Den Regler wirklich BEWEGEN — ``QSlider.setValue`` loest das Signal
        aus, das der Nutzer ausloest (``_on_value_changed``), und der entscheidet
        selbst, welche Geraete er anfasst.

        ``_apply_value(fid, …)`` waere hier die Seitentuer: sie SETZT das Geraet,
        statt zu messen, ob der Regler es ueberhaupt anfasst."""
        self._grundstellung(*fids)
        vorher = {fid: self._dmx(fid) for fid in fids}
        slider._slider.setValue(wert)
        return {fid: {k: v for k, v in self._dmx(fid).items()
                      if vorher[fid].get(k) != v} for fid in fids}

    # ── FM-27 am Schnellwahl-Regler ──────────────────────────────────────
    def test_kein_speed_regler_traegt_ein_geraet_ohne_speed(self):
        """``MOVBAR4 [22-Kanal]`` hat keinen ``speed``-Kanal, die
        ``HYDRABEAM 19ch`` schon. KEIN gebauter ``speed``-Regler darf die
        MOVBAR4 tragen — auch nicht der der Schnellwahl."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(2, "HYDRA4000", 19)
        self.assertNotIn("speed", {(c.attribute or "") for c
                                   in get_channels_for_patched(self._fx(1))})
        regler = self._regler(["1:0", "2:0"], "speed")
        self.assertTrue(regler, "es gibt gar keinen speed-Regler mehr")
        for kopf, fids, _s in regler:
            self.assertNotIn(1, fids,
                             f"Regler (Kopf {kopf}) traegt die MOVBAR4, die "
                             f"gar keinen speed-Kanal hat")

    def test_schnellwahl_speed_kommt_am_geraet_ohne_kanal_nicht_an(self):
        """★★ Der gemeldete Schaden am Ausgang: ein Zug am „Pan/Tilt-Speed"-
        Regler schrieb ``speed=177`` ins Programmer-Dict der MOVBAR4 und
        bewegte dort **keinen einzigen** DMX-Kanal — stille Klasse FM-9/A5."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(2, "HYDRA4000", 19)
        # Der geraeteweite speed-Regler ist der der Schnellwahl: der Bucket-Weg
        # liefert bei gewaehlten Kopf-Zellen einen Kopf-Regler (head=0).
        frei = [s for kopf, _f, s in self._regler(["1:0", "2:0"], "speed")
                if kopf is None]
        self.assertTrue(frei, "die Schnellwahl baut ihren speed-Regler nicht mehr")
        d = self._zieh_am_regler(frei[0], (1, 2), 177)
        self.assertEqual(d[1], {}, "die MOVBAR4 hat keinen speed-Kanal — an ihr "
                                   "darf sich nichts bewegen")
        self.assertEqual(d[2].get("Head Speed"), 177,
                         "an der HYDRABEAM muss der Regler weiter wirken")
        self.assertIsNone(self._state_wert(1, "speed"),
                          "der Wert darf auch nicht im Programmer-Dict landen — "
                          "genau das war der stumme Rest")

    def test_positivkontrolle_beide_haben_speed(self):
        """★ Der Waechter darf nicht alles beanstanden: haben BEIDE Geraete den
        Kanal, treibt derselbe Regler auch beide."""
        self._patch(1, "HYDRA4000", 19)
        self._patch(2, "HYDRA4000", 19)
        frei = [s for kopf, _f, s in self._regler(["1:0", "2:0"], "speed")
                if kopf is None]
        self.assertTrue(frei)
        d = self._zieh_am_regler(frei[0], (1, 2), 177)
        for fid in (1, 2):
            self.assertEqual(d[fid].get("Head Speed"), 177,
                             f"Geraet {fid} wurde ausgesperrt, obwohl es den "
                             f"Kanal hat")

    # ── FM-27 an den Farb-Synchronreglern ────────────────────────────────
    def test_farb_synchronregler_laesst_geraete_ohne_die_farbe_heraus(self):
        """``SHARPY [16-Kanal]`` hat kein ``color_r`` (Farbrad statt RGB), der
        ``Robin Spiider [91-Kanal Pixel]`` schon. Der Regler „Grundfarbe Rot"
        zeigte beide an und bewegte am SHARPY nichts."""
        self._patch(2, "SPIIDER", 91)
        self._patch(3, "SHARPY", 16)
        self.assertNotIn("color_r", {(c.attribute or "") for c
                                     in get_channels_for_patched(self._fx(3))})
        regler = self._regler(["2", "3"], "color_r")
        self.assertTrue(regler, "der Rot-Regler ist ganz verschwunden")
        for _kopf, fids, _s in regler:
            self.assertNotIn(3, fids, "der SHARPY hat kein color_r")
        d = self._zieh_am_regler(regler[0][2], (2, 3), 200)
        self.assertEqual(d[3], {}, "am SHARPY darf sich nichts bewegen")
        self.assertEqual(d[2].get("Grundfarbe Rot"), 200,
                         "am Spiider muss der Regler weiter wirken")
        self.assertIsNone(self._state_wert(3, "color_r"))

    def test_positivkontrolle_beide_haben_die_farbe(self):
        """★ Zwei Geraete mit RGB: der Synchronregler treibt weiter beide."""
        self._patch(2, "SPIIDER", 91)
        self._patch(3, "MOVBAR4", 22)
        self.assertIn("color_r", {(c.attribute or "") for c
                                  in get_channels_for_patched(self._fx(3))})
        regler = self._regler(["2", "3"], "color_r")
        self.assertTrue(regler)
        traeger = {fid for _k, fids, _s in regler for fid in fids}
        self.assertEqual(traeger, {2, 3},
                         "ein Geraet MIT der Farbe wurde ausgesperrt")

    def _state_wert(self, fid: int, attr: str):
        return self.state.get_programmer_value(fid, attr, head=None)


class AltlastKopfZelleAufDemMidiWegTest(_Basis):
    """★★ Was die neue Zaehlung mit einer Kopf-Zelle macht, die es NICHT MEHR
    gibt — der ungemessene Rest aus der Gegenpruefung zu #663.

    Die Zelle ``1:4`` einer ``HYDRABEAM 19ch`` ist ueber die Oberflaeche nicht
    erzeugbar (die Geraeteliste bietet 4 Kopf-Zeilen, die Kommandozeile weist
    ``1:5`` ab). Sie kann aber als **Altlast** in einer gespeicherten Gruppe
    stehen: Kopf-Zellen ueberleben einen Kanal-Modus-Wechsel, ``update_fixture``
    raeumt die Auto-Gruppe nicht auf (s. ``validate_head_restrictions``).

    Vorher schrieb dieselbe Zelle ueber ``intensity#4`` auf CH18 „Kopf 4 Dimmer"
    — also auf den Kanal, den der Regler „K4" schon hatte. Jetzt greift die
    dokumentierte Klemm-Regel: bleibt nach dem Klemmen kein gueltiger Kopf,
    faellt das Geraet in den GERAETEWEITEN Bestandspfad. Das ist eine
    Verhaltensaenderung auf der Buehne und wird deshalb hier festgehalten —
    gemessen am DMX-Ausgang, auf dem echten MIDI-Weg.
    """

    def _midi(self):
        from src.core.midi import midi_mapper as mm

        class _NoMidi:
            def subscribe(self, cb):
                pass

            def send_note(self, *a, **k):
                pass

            def send_cc(self, *a, **k):
                pass

            def open_output(self, *a, **k):
                pass

            def current_output_name(self):
                return ""

        orig = mm.get_midi_manager
        mm.get_midi_manager = lambda: _NoMidi()
        m = mm.MidiMapper(self.state)

        def _restore():
            try:
                m.close()
            except Exception:
                pass
            mm.get_midi_manager = orig

        self.addCleanup(_restore)
        m.add_mapping(mm.MidiMapping(
            name="Dimmer", msg_type="cc", channel=1, data1=7,
            action=mm.ACTION_PROGRAMMER_VAL, param="intensity",
            button_mode=mm.BUTTON_CONTINUOUS))
        return m, mm

    def _fahre(self, cells, data2: int = 127) -> dict:
        """Eine echte MIDI-Nachricht einspeisen (``_on_midi`` ist der Einstieg,
        den der MIDI-Manager aufruft) und den DMX-Ausgang ablesen."""
        m, mm = self._midi()
        self.state.set_selected_cells(list(cells))
        self._grundstellung(1)
        m._on_midi(mm.MidiMessage(port_name="T", channel=1, msg_type="cc",
                                  data1=7, data2=data2))
        self.state._flush_programmer_to_dmx(1)
        return self._dmx(1)

    def test_erreichbare_kopfzelle_trifft_weiter_genau_ihren_dimmer(self):
        """★ Positivkontrolle — und der Bestandsfall, auf den es ankommt: die
        ueber die Geraeteliste erreichbaren Zellen ``1:0``…``1:3`` verhalten
        sich unveraendert."""
        self._patch(1, "HYDRA4000", 19)
        dmx = self._fahre(["1:2"])
        self.assertEqual(dmx["Kopf 3 Dimmer"], 255)
        for anderer in ("Kopf 1 Dimmer", "Kopf 2 Dimmer", "Kopf 4 Dimmer"):
            self.assertEqual(dmx[anderer], 0, f"{anderer} zieht mit")

    def test_altlast_zelle_faellt_auf_das_ganze_geraet(self):
        """Die Zelle ``1:4`` nennt einen Kopf, den es an diesem Geraet nicht
        gibt. Sie wird geklemmt, es bleibt kein gueltiger Kopf — also
        geraeteweit. **Alle vier Koepfe** gehen hoch, nicht nur einer; wer diese
        Altlast in einer Gruppe hat, merkt den Unterschied auf der Buehne."""
        self._patch(1, "HYDRA4000", 19)
        dmx = self._fahre(["1:4"])
        self.assertEqual(dmx["Master Dimmer"], 255)
        for kopf in ("Kopf 1 Dimmer", "Kopf 2 Dimmer", "Kopf 3 Dimmer",
                     "Kopf 4 Dimmer"):
            self.assertEqual(dmx[kopf], 255,
                             f"{kopf} muesste beim geraeteweiten Rueckfall "
                             f"mitkommen")


class KeineErreichbareKopfZelleVerliertIhrenKopfTest(unittest.TestCase):
    """★★ Die BESTANDS-Frage, ueber die ganze echte Bibliothek gemessen.

    Die neue Zaehlung faellt fuer 41 Modi niedriger aus als die alte (FM-29,
    geteilter Master). Die Frage ist nicht „aendert sich etwas", sondern:
    **verliert dadurch eine Kopf-Zelle ihren Kopf, die der Nutzer ueberhaupt
    erzeugen kann?** Erreichbar sind die Kopf-Zeilen der Geraeteliste,
    ``max(Farbbaenke, Pan/Tilt-Koepfe)`` (``ProgrammerView._head_row_count``) —
    darueber hinaus gibt es keinen Bedienweg.

    Der Test rechnet die ALTE Zaehlung (Vorkommen) hier woertlich nach und
    verlangt fuer jedes ``(Modus, Attribut)``-Paar: die neue Antwort darf nicht
    unter ``min(alt, erreichbare Koepfe)`` fallen. Gemessen ueber **33.980
    Paare in 5.122 Modi**: kein einziger Verlust.

    ``raw`` ist ausgenommen — dort ist der Wegfall der Kopf-Achse der ERKLAERTE
    Zweck von FM-28 (``attr_has_head_axis``), und ``FM28RawBekommtKeinenKopf
    ReglerTest`` misst ihn.

    Nur lesend auf der Bibliothek; eine Sammelabfrage statt einer Abfrage je
    Modus, damit der Durchlauf unter zwei Sekunden bleibt."""

    def test_bibliothek_weit_keine_erreichbare_zelle_verliert_ihren_kopf(self):
        from collections import defaultdict

        from src.core.app_state import (color_head_count_for_channels,
                                        move_head_count_for_channels)
        from src.core.database.models import FixtureChannel

        ensure_builtins()

        def alte_zaehlung(chans, a):
            n = sum(1 for c in chans
                    if (getattr(c, "attribute", "") or "").lower() == a)
            return n if n >= 1 else 1

        with Session(fdb_engine()) as s:
            namen = {mid: f"{short} [{cc}ch] {mname}" for mid, mname, cc, short
                     in s.execute(
                         select(FixtureMode.id, FixtureMode.name,
                                FixtureMode.channel_count,
                                FixtureProfile.short_name)
                         .join(FixtureProfile,
                               FixtureProfile.id == FixtureMode.fixture_id)).all()}
            kanaele = defaultdict(list)
            for c in s.execute(select(FixtureChannel).order_by(
                    FixtureChannel.mode_id,
                    FixtureChannel.channel_number)).scalars():
                kanaele[c.mode_id].append(c)
            s.expunge_all()

        self.assertGreater(len(kanaele), 1000,
                           "die Bibliothek ist leer — der Test wuerde nichts "
                           "messen und trotzdem gruen sein")
        verlust, paare = [], 0
        for mid, chans in kanaele.items():
            erreichbar = max(int(color_head_count_for_channels(None, chans)),
                             int(move_head_count_for_channels(None, chans)))
            for a in sorted({(getattr(c, "attribute", "") or "").lower()
                             for c in chans} - {"", "raw"}):
                paare += 1
                alt = alte_zaehlung(chans, a)
                neu = int(attr_head_count_for_channels(None, chans, a))
                if neu < min(alt, erreichbar):
                    verlust.append(f"{namen.get(mid, mid)} attr={a} "
                                   f"{alt}->{neu}, erreichbar {erreichbar}")
        self.assertGreater(paare, 10000, "zu wenige Paare geprueft")
        self.assertEqual(verlust[:10], [],
                         f"{len(verlust)} (Modus, Attribut)-Paare verlieren "
                         f"einen ERREICHBAREN Kopf")


if __name__ == "__main__":
    unittest.main()
