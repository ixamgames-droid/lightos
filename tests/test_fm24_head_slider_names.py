"""FM-24 — Pro-Kopf-Regler trugen den Kanalnamen der VORLAGE.

Die Attribut-Regler des Programmers werden aus ``_template_channels`` gebaut.
Diese Vorlage ist pro Attribut **dedupliziert**: uebrig bleibt das erste
Vorkommen (bevorzugt eines mit ``ranges``). An einem Mehrkopf-Geraet gehoert
dieser Name damit einem ANDEREN Kopf als dem, den der Regler treibt — an jedem
Mehrkopf-Geraet, nicht nur an den neuen Pixel-Ringen.

Gemessen am Bestand (alles Builtins, damit der Test nicht an einer lokal
importierten Library haengt):

===========================================  =========================  ===========================
Geraet / gewaehlter Kopf                     Aufschrift VORHER          geschriebener Kanal
===========================================  =========================  ===========================
``MOVBAR4 [22ch]``, Kopf 4, ``pan``          „Kopf 1 Pan · K4"          CH16 „Kopf 4 Pan"
``HYDRABEAM 4000 [19ch]``, Kopf 1, Dimmer    „Master Dimmer · K1"       CH9 „Kopf 1 Dimmer"
``Robin Spiider [91ch Pixel]``, Kopf 3, raw  „Grundfarbe Shutter · K3"  CH11 „Grundfarbe Gruen Fein"
===========================================  =========================  ===========================

Der Spiider-Fall zeigt die Fehlerart am deutlichsten: der Name nannte einen
DRITTEN Kanal — weder den eigenen noch den, der zufaellig Kopf 1 gehoert.
Seit **FM-28** (2026-08-24) wird dieser Regler gar nicht mehr gebaut: ``raw``
ist kein Kopf-Attribut. Der zugehoerige Test misst jetzt seine Abwesenheit.

Die Zusage dieses Items ist deshalb bewusst am Ausgang festgemacht und nicht an
erwarteten Zeichenketten: **jeder Pro-Kopf-Regler traegt den Namen des Kanals,
den er wirklich schreibt.** Der Vergleichswert kommt aus
``programmer_key_for_head`` + ``channel_occurrence_keys`` — genau der Weg, den
``AttributeSlider._apply_value`` -> ``AppState.set_programmer_value(head=…)``
zum Schreiben geht. ``KopfReglerNennenIhrenKanalTest`` misst das ueber ALLE
Pro-Kopf-Regler ALLER Koepfe von sechs Auswahlen (auch die Farb- und
Tilt-Bloecke, die den geaenderten Zweig gar nicht benutzen) und laesst sich die
Zahl der gemessenen Regler quittieren, damit eine leere Messung nicht als
Erfolg durchgeht.

Positivkontrolle: Einkopf-Geraete sind die Mehrheit und duerfen sich NICHT
aendern — dort darf gar kein Anzeigename gesetzt werden
(``EinkopfBleibtUnveraendertTest``), und ein Mehrkopf-Geraet OHNE Kopf-Auswahl
ebenso wenig.

★ Nachbesserung (Gegenpruefung zur ersten Runde): der RUECKFALL — der erste
Besitzer hat das Attribut gar nicht — war in einer Konstellation festgenagelt,
in der der Vorlagen-Name zufaellig WAHR ist (``MOVBAR4`` + ``HYDRABEAM``, beide
Kopf 1: die Vorlage kommt aus der Hydrabeam, und die steckt im selben Regler).
``RueckfallTest`` baut jetzt die Auswahl, in der ein falscher Name wirklich
entsteht: ein GANZ gewaehltes drittes Geraet stellt die Vorlage, steht aber
nicht in den Besitzern. Gemessen an ``SHARPY`` ganz + ``MOVBAR4`` K1 +
``HYDRABEAM`` K1 hiess der ``speed``-Regler vorher „P/T-Speed · K1" — ein Kanal
des Sharpy, den dieser Regler gar nicht treibt.

★★ **FM-27** (2026-08-24) hat dieser Klasse die Grundlage entzogen: ein Geraet
ohne den Kanal steckt gar nicht mehr im Regler. ``RueckfallTest`` misst deshalb
jetzt die staerkere Zusage — jeder Besitzer hat den Kanal wirklich, und hat ihn
keiner, entsteht der Regler nicht.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel                  # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import (channel_occurrence_keys,            # noqa: E402
                                get_channels_for_patched, get_state,
                                programmer_key_for_head)
from src.core.database.fixture_db import (engine as fdb_engine,     # noqa: E402
                                          ensure_builtins)
from src.core.database.models import (FixtureMode, FixtureProfile,  # noqa: E402
                                      PatchedFixture)
from src.core.show.show_file import reset_show                      # noqa: E402
from src.ui.views.programmer_view import (AttributeSlider,          # noqa: E402
                                          ProgrammerView)

_SUFFIX = " · K"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _aufschrift(slider) -> str:
    """Was am Regler STEHT — der Text des QLabels im Widget.

    ★ Bewusst nicht ``slider._display_name``: das ist der Wert, den die View
    hineinreicht. Gelesen wird, was ``AttributeSlider._setup_ui`` daraus
    tatsaechlich anschreibt — sonst bliebe der Weg vom Namen zur Aufschrift
    ungemessen (gegengeprueft: laesst man ``_setup_ui`` wieder ``_channel.name``
    anschreiben, wird dieser Test rot)."""
    lbls = [w for w in slider.findChildren(QLabel)
            if w is not slider._lbl_val and w is not slider._lbl_pct]
    assert len(lbls) == 1, f"{len(lbls)} Beschriftungen am Regler gefunden"
    return lbls[0].text()


def _pid(short: str) -> int:
    """Profil-ID ueber den KURZnamen eines Builtins (nie ueber den Anzeigenamen —
    der existiert je nach Rechner nur lokal, Fallenklasse QA-23)."""
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


def _mode_name(short: str, channels: int) -> str:
    """Modusname ueber die KANALZAHL — die Anzeigenamen der Modi sind Fliesstext
    („22-Kanal 4×Move RGB"), und dieser Test darf nicht an ihrer Schreibweise
    haengen."""
    with Session(fdb_engine()) as s:
        return s.execute(select(FixtureMode.name).where(
            FixtureMode.fixture_id == _pid(short),
            FixtureMode.channel_count == channels)).scalars().first()


class _Basis(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self._addr = 1

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

    def _slider_objs(self, cells) -> list:
        """Die gebauten ``AttributeSlider`` einer Auswahl — der echte Bauweg
        (View + ``set_selected_cells``), nicht ein direkter Aufruf der
        Beschriftungsfunktion.

        Frische View je Messung — eine wiederverwendete View liefert per
        ``findChildren`` auch die Regler frueherer Auswahlen (Qt loescht sie
        erst spaeter)."""
        v = ProgrammerView()
        self.addCleanup(v.deleteLater)
        self.state.set_selected_cells(list(cells))
        _app().processEvents()
        return v.findChildren(AttributeSlider)

    def _regler(self, cells) -> list:
        """``(attribut, kopf, aufschrift, anzeigename, fids)`` je Attribut-Regler.
        ``aufschrift`` ist der angeschriebene Text, ``anzeigename`` der von der
        View gesetzte Wert (``None`` = geraeteweiter Regler)."""
        return [(s._channel.attribute, s._head,
                 _aufschrift(s), s._display_name,
                 tuple(f.fid for f in s._fixtures))
                for s in self._slider_objs(cells)]

    def _kanalname(self, fx, attr: str, head: int):
        """Name des Kanals, den ``set_programmer_value(fid, attr, …, head=head)``
        an diesem Geraet trifft — die unabhaengige Gegenrechnung zur Aufschrift.
        ``None``, wenn das Geraet diesen Kanal gar nicht hat."""
        chans = get_channels_for_patched(fx)
        key = programmer_key_for_head(chans, attr, head)
        return next((c.name for c, k in channel_occurrence_keys(chans)
                     if k == key), None)


class GemeldeteSymptomeTest(_Basis):
    """Die drei gemessenen Faelle aus dem Backlog-Eintrag, namentlich."""

    def test_movbar4_kopf4_heisst_kopf_4(self):
        self._patch(1, "MOVBAR4", 22)
        auf = {a: t for a, h, t, _d, _f in self._regler(["1:3"]) if h == 3}
        self.assertEqual(auf.get("pan"), "Kopf 4 Pan · K4")
        self.assertEqual(auf.get("tilt"), "Kopf 4 Tilt · K4")

    def test_hydrabeam_kopf1_nennt_den_kopfdimmer_nicht_den_master(self):
        """★ Der Fall, den FM-17 im SCHREIBWEG schon geloest hat: „Kopf 1"
        adressiert ueber die Kopf-Karte CH9, die Aufschrift nannte aber weiter
        den geteilten CH1 „Master Dimmer" — also genau den Kanal, dessen
        Verwechslung FM-17 ausgeraeumt hat."""
        self._patch(1, "HYDRA4000", 19)
        auf = {a: t for a, h, t, _d, _f in self._regler(["1:0"]) if h == 0}
        self.assertEqual(auf.get("intensity"), "Kopf 1 Dimmer · K1")

    def test_spiider_pixel_baut_fuer_raw_gar_keinen_kopf_regler(self):
        """Am Spiider im Pixel-Modus tragen 21 verschiedene Funktionen das
        Sammel-Attribut ``raw``; die Vorlage zog davon „Grundfarbe Shutter"
        heran, geschrieben wurde ``raw#2`` = CH11 „Grundfarbe Grün Fein".

        ★ FM-24 hat die Aufschrift auf den wirklich geschriebenen Kanal
        umgestellt („Grundfarbe Grün Fein · K3") — wahr, aber sinnlos: ein
        „Kopf 3", der ein Feinbyte einer Grundfarbe verstellt, ist kein Kopf.
        Seit FM-28 (2026-08-24) entsteht dieser Regler gar nicht mehr; ``raw``
        wird ausschliesslich geraeteweit bedient."""
        self._patch(1, "SPIIDER", 91)
        regler = self._regler(["1:2"])
        self.assertEqual(
            [(a, h, t) for a, h, t, _d, _f in regler if a == "raw" and h is not None],
            [], "fuer ``raw`` darf kein Pro-Kopf-Regler gebaut werden")
        self.assertTrue(
            [a for a, h, _t, _d, _f in regler if a == "raw" and h is None],
            "der geraeteweite raw-Regler muss bleiben — sonst waeren die "
            "unerkannten Kanaele gar nicht mehr bedienbar")


class KopfReglerNennenIhrenKanalTest(_Basis):
    """★★ Die volle Zusage, an sechs Auswahlen und ueber ALLE Koepfe.

    Nicht „der String stimmt", sondern: der Name gehoert zu dem Kanal, den
    dieser Regler an diesem Kopf schreibt. Regler mit mehreren Geraeten duerfen
    naturgemaess nur EINEN Namen tragen — dort wird verlangt, dass er von einem
    der getriebenen Geraete stammt, und zwar von DIESEM Kopf.
    """

    def _pruefe(self, cells, mindestens: int) -> int:
        gemessen = 0
        for attr, head, auf, _disp, fids in self._regler(cells):
            if head is None:
                continue
            gemessen += 1
            erwartet = [self._kanalname(self._fx(fid), attr, head)
                        for fid in fids]
            kandidaten = [n for n in erwartet if n]
            self.assertTrue(
                kandidaten,
                f"{cells}: Regler {attr}/K{head + 1} treibt {fids}, aber KEINES "
                f"dieser Geraete hat dafuer einen Kanal")
            erlaubt = kandidaten + [f"{n}{_SUFFIX}{head + 1}"
                                    for n in kandidaten]
            self.assertIn(
                auf, erlaubt,
                f"{cells}: Regler {attr}/K{head + 1} heisst {auf!r}, schreibt "
                f"aber {erwartet!r}")
        self.assertGreaterEqual(
            gemessen, mindestens,
            f"{cells}: nur {gemessen} Pro-Kopf-Regler gemessen — eine leere "
            f"Messung darf nicht als Erfolg durchgehen")
        return gemessen

    def test_movbar4_alle_vier_koepfe(self):
        self._patch(1, "MOVBAR4", 22)
        for h in range(4):
            self._pruefe([f"1:{h}"], mindestens=5)   # pan, tilt, r, g, b

    def test_hydrabeam_19ch_geteilter_master(self):
        self._patch(1, "HYDRA4000", 19)
        for h in range(4):
            self._pruefe([f"1:{h}"], mindestens=3)   # pan, tilt, intensity

    def test_hydrabeam_56ch_pro_kopf_shutter(self):
        """Ohne geteilten Master: „Kopf 1" landet dort auf dem BASIS-Schluessel
        (FM-18) — auch dieser Regler muss seinen eigenen Kanal nennen."""
        self._patch(1, "HYDRA4000", 56)
        for h in range(4):
            self._pruefe([f"1:{h}"], mindestens=5)

    def test_spiider_pixel_alle_ringe(self):
        self._patch(1, "SPIIDER", 91)
        for h in (0, 1, 5, 10, 19):
            self._pruefe([f"1:{h}"], mindestens=3)

    def test_parbar_ohne_bewegung(self):
        self._patch(1, "PARBAR4", 16, ftype="par")
        for h in range(4):
            self._pruefe([f"1:{h}"], mindestens=4)   # r, g, b, w

    def test_name_kommt_vom_getriebenen_geraet_nicht_vom_ersten_gewaehlten(self):
        """★ Ein Geraet, das diesen Kopf gar nicht hat, faellt aus dem Regler
        heraus (``_slider_head_buckets``) — dann darf auch sein Name nicht mehr
        drankommen, obwohl es in der Auswahl VORN steht und die Vorlage stellt.

        Gemessen: ``SHARPY`` (1 Pan, „Pan") vor ``MOVBAR4`` (4 Pans). Der
        Kopf-2-Pan-Regler treibt nur die Bar und muss „Kopf 2 Pan" heissen,
        nicht das „Pan" des Sharpy."""
        self._patch(1, "SHARPY", 16)
        self._patch(2, "MOVBAR4", 22)
        treffer = [(auf, fids) for attr, h, auf, _d, fids
                   in self._regler(["1:1", "2:1"])
                   if attr == "pan" and h == 1]
        self.assertTrue(treffer, "kein Pan-Kopf-Regler gebaut")
        auf, fids = treffer[0]
        self.assertEqual(fids, (2,),
                         "der Sharpy hat keinen zweiten Pan-Kopf und darf in "
                         "diesem Regler gar nicht stecken")
        self.assertEqual(auf, "Kopf 2 Pan · K2")

    def test_gemischte_auswahl_spider_und_bar(self):
        """Gemischt ist der Fall, in dem der Tilt-Block (eigener Bauweg) und die
        allgemeinen Regler NEBENEINANDER stehen — beide muessen stimmen."""
        self._patch(1, "MOVBAR4", 22)
        # ★ "SPIIDER" mit 27 Kanaelen, nicht "Speider" mit 14: letzteres ist ein
        # LOKAL importiertes
        # Profil (Tippfehler im Namen) und existiert nur auf Robins Rechner.
        # In der CI mit frisch geseedeter Bibliothek lieferte die Suche `None`,
        # und `int(None)` warf — der Test war auf diesem Rechner gruen und dort
        # rot. Genau die Fallenklasse, vor der der Kommentar an `_pid` warnt:
        # er nennt den Anzeigenamen, aber ein KURZname kann ebenso lokal sein.
        self._patch(2, "SPIIDER", 27, ftype="spider")
        self._pruefe(["1:1", "2:1"], mindestens=4)


class EinkopfBleibtUnveraendertTest(_Basis):
    """★ Positivkontrolle: die Mehrheit der Geraete darf sich NICHT ruehren.

    Gemessen wird nicht „sieht plausibel aus", sondern dass der geaenderte Zweig
    ueberhaupt nicht betreten wird: kein Regler bekommt einen Anzeigenamen, kein
    Regler traegt ein Kopf-Suffix, jede Aufschrift ist der rohe Kanalname.
    """

    def _erwarte_unberuehrt(self, cells, mindestens: int):
        regler = self._regler(cells)
        self.assertGreaterEqual(len(regler), mindestens,
                                f"{cells}: zu wenige Regler gemessen")
        for attr, head, auf, disp, _fids in regler:
            self.assertIsNone(
                disp, f"{cells}: {attr} hat den Anzeigenamen {disp!r} bekommen "
                      f"— hier darf nichts umbenannt werden")
            self.assertIsNone(head, f"{cells}: {attr} wurde an Kopf {head} "
                                    f"gebunden")
            self.assertNotIn(_SUFFIX, auf, f"{cells}: {attr} traegt {auf!r}")

    def test_moving_head_einkopf(self):
        self._patch(1, "SHARPY", 16)
        self._erwarte_unberuehrt(["1"], mindestens=10)

    def test_par_einkopf(self):
        self._patch(1, "FLATPRO7", 8, ftype="par")
        self._erwarte_unberuehrt(["1"], mindestens=4)

    def test_einkopf_auch_mit_kopf_zelle_in_der_auswahl(self):
        """Eine Kopf-Zelle auf einem Einkopf-Geraet (Gruppen-Raster) darf nichts
        VERDREHEN — es gibt dort nur den einen Kanal, und der muss dranstehen."""
        self._patch(1, "SHARPY", 16)
        gemessen = 0
        for attr, head, auf, _disp, _fids in self._regler(["1:0"]):
            if head is None:
                continue
            gemessen += 1
            self.assertEqual(auf, f"{self._kanalname(self._fx(1), attr, 0)}"
                                  f"{_SUFFIX}1")
        self.assertGreater(gemessen, 0, "kein Kopf-Regler gemessen")

    def test_mehrkopf_ohne_kopfauswahl_unveraendert(self):
        """Der haeufigste Mehrkopf-Fall: ganzes Geraet gewaehlt. Auch dann bleibt
        alles geraeteweit und unbenannt — die Aenderung greift ausschliesslich,
        wenn wirklich ein Kopf gewaehlt ist."""
        self._patch(1, "MOVBAR4", 22)
        for attr, _head, auf, disp, _fids in self._regler(["1"]):
            if attr.startswith("color_"):
                continue      # Synchron-Farbregler tragen ihr eigenes Label
            self.assertIsNone(disp, f"{attr} wurde umbenannt")
            self.assertNotIn(_SUFFIX, auf)


class RueckfallTest(_Basis):
    """Der erste Besitzer eines Reglers hat das Attribut gar nicht — woher darf
    der Name dann kommen?

    ★★ **Seit FM-27 (2026-08-24) kann das gar nicht mehr passieren.** Damals
    behielt ``_slider_head_buckets`` fuer Kopf 1 auch ein Geraet, das den Kanal
    ueberhaupt nicht hat (``attr_head_count_for_channels`` antwortete fuer ein
    FEHLENDES Attribut ``1``). Der Rueckfall auf den VORLAGEN-Namen war darauf
    die falsche Antwort: die Vorlage ist ueber die GANZE Auswahl dedupliziert
    und kann aus einem Geraet stammen, das dieser Regler nicht treibt. FM-24 hat
    daraufhin ALLE Besitzer der Reihe nach gefragt — FM-27 nimmt die Frage weg,
    indem so ein Geraet gar nicht mehr in den Regler kommt.

    Diese Klasse misst deshalb jetzt die staerkere Zusage: **jeder Besitzer
    eines Pro-Kopf-Reglers hat den Kanal wirklich**, und der Name kommt vom
    ersten. Die Suche ueber alle Besitzer und der Attribut-Rueckfall in
    ``_head_slider_label`` bleiben als Absicherung im Code stehen; erreichbar
    sind sie ueber die Oberflaeche nicht mehr.
    """

    def _kopfregler(self, cells, attr: str, head: int = 0):
        """Der EINE Pro-Kopf-Regler dieses Attributs: ``(slider, aufschrift,
        fids)``. Der Vorlagen-Kanal haengt als ``slider._channel`` dran — genau
        das Objekt, aus dem die Aufschrift frueher kam."""
        treffer = [s for s in self._slider_objs(cells)
                   if s._channel.attribute == attr and s._head == head]
        self.assertEqual(
            len(treffer), 1,
            f"{cells}: {len(treffer)} Pro-Kopf-Regler fuer {attr}/K{head + 1} "
            f"— erwartet genau einer")
        s = treffer[0]
        return s, _aufschrift(s), tuple(f.fid for f in s._fixtures)

    def test_geraet_ohne_den_kanal_steckt_nicht_mehr_im_regler(self):
        """★ FM-27, an derselben Auswahl wie frueher gemessen: MOVBAR4 (kein
        ``speed``) vor HYDRABEAM (CH19 „Head Speed"), beide Kopf 1.

        Vorher trieb der ``speed``-Regler **beide** Geraete — bei der MOVBAR4
        landete der Wert im Programmer-Dict und nirgends auf DMX. Jetzt bleibt
        nur das Geraet uebrig, das den Kanal hat, und der Name kommt von ihm."""
        self._patch(1, "MOVBAR4", 22)          # kein speed-Kanal
        self._patch(2, "HYDRA4000", 19)        # CH19 „Head Speed"
        _s, auf, fids = self._kopfregler(["1:0", "2:0"], "speed")
        self.assertIsNone(
            self._kanalname(self._fx(1), "speed", 0),
            "MOVBAR4 muss dieses Attribut fehlen — sonst misst der Test den "
            "Fall gar nicht")
        self.assertEqual(fids, (2,),
                         "die MOVBAR4 hat keinen speed-Kanal und darf in diesem "
                         "Regler nicht mehr stecken")
        self.assertEqual(auf, f"Head Speed{_SUFFIX}1")

    def test_vorlage_aus_nicht_getriebenem_geraet_wird_nicht_genannt(self):
        """★★ Die Kante, an der es zaehlt: das VORLAGEN-Geraet steht nicht in
        den Besitzern.

        Ein ``SHARPY [16-Kanal]`` GANZ gewaehlt (eigener geraeteweiter Regler,
        Vorlage fuer ``speed`` = CH7 „P/T-Speed") und dazu Kopf 1 von
        ``MOVBAR4`` + ``HYDRABEAM 19ch``. Der Kopf-1-Regler treibt davon nur die
        Hydrabeam (die MOVBAR4 hat den Kanal nicht und faellt seit FM-27 ganz
        heraus). Gemessen vor der Nachbesserung: „**P/T-Speed** · K1" — der
        Kanal eines Geraets, das dieser Regler nicht anfasst, waehrend
        „Head Speed" der getriebenen Hydrabeam ungenutzt danebenlag."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(2, "HYDRA4000", 19)
        self._patch(3, "SHARPY", 16)
        s, auf, fids = self._kopfregler(["3", "1:0", "2:0"], "speed")
        fremd = self._kanalname(self._fx(3), "speed", 0)
        eigen = self._kanalname(self._fx(2), "speed", 0)
        # Konstellation nachweisen, sonst misst der Test etwas anderes:
        self.assertNotIn(3, fids,
                         "der Sharpy ist GANZ gewaehlt und hat seinen eigenen "
                         "geraeteweiten Regler — steckt er hier drin, ist die "
                         "Kante nicht gemessen")
        self.assertEqual(s._channel.name, fremd,
                         "die Vorlage dieses Reglers muss vom Sharpy kommen — "
                         "sonst gibt es gar keinen fremden Namen zu vermeiden")
        self.assertIsNone(self._kanalname(self._fx(1), "speed", 0),
                          "MOVBAR4 muss das Attribut fehlen")
        self.assertNotEqual(fremd, eigen,
                            "beide Kanaele heissen gleich — dann waere jede "
                            "Aufschrift zufaellig wahr")
        self.assertNotEqual(auf, f"{fremd}{_SUFFIX}1",
                            f"der Regler treibt {fids} und nennt trotzdem den "
                            f"Kanal des Sharpy")
        self.assertEqual(auf, f"{eigen}{_SUFFIX}1")

    def test_ohne_besitzerkanal_entsteht_gar_kein_kopf_regler(self):
        """★ Und wenn KEIN Geraet der Kopf-Auswahl den Kanal hat, gab es keinen
        wahren Kanalnamen — FM-24 schrieb dann das ATTRIBUT dran („Speed · K1")
        statt des fremden „P/T-Speed" aus der Vorlage.

        Seit FM-27 gibt es diesen Regler nicht mehr: dieselbe Auswahl, aber die
        einzige Kopf-Zelle gehoert der MOVBAR4, die keinen ``speed``-Kanal hat.
        Ein Regler, der nichts ausgeben kann, wird gar nicht erst gebaut — der
        geraeteweite Regler des GANZ gewaehlten Sharpy bleibt daneben stehen."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(3, "SHARPY", 16)
        self.assertIsNone(self._kanalname(self._fx(1), "speed", 0),
                          "MOVBAR4 darf diesen Kanal nicht haben — sonst misst "
                          "der Test den Fall gar nicht")
        regler = [(h, fids) for a, h, _t, _d, fids
                  in self._regler(["3", "1:0"]) if a == "speed"]
        self.assertEqual([r for r in regler if r[0] is not None], [],
                         "kein Geraet der Kopf-Auswahl hat den Kanal — dann "
                         "darf auch kein Pro-Kopf-Regler entstehen")
        self.assertIn((None, (3,)), regler,
                      "der geraeteweite Regler des Sharpy muss bleiben, und "
                      "zwar OHNE die MOVBAR4 (FM-27 gilt auch dort)")

    def test_erster_besitzer_hat_vorrang(self):
        """★ Positivkontrolle zur Suche: haben MEHRERE Besitzer den Kanal, gilt
        der ERSTE — die Suche darf sich nicht irgendeinen greifen.

        ``MOVBAR4`` (ein einziges ``intensity``-Vorkommen, Kopf 1 schreibt also
        den Basis-Schluessel CH21 „Master Dimmer") vor ``HYDRABEAM 19ch``
        (Kopf-Karte -> ``intensity#1`` = CH9 „Kopf 1 Dimmer")."""
        self._patch(1, "MOVBAR4", 22)
        self._patch(2, "HYDRA4000", 19)
        _s, auf, fids = self._kopfregler(["1:0", "2:0"], "intensity")
        erster = self._kanalname(self._fx(1), "intensity", 0)
        zweiter = self._kanalname(self._fx(2), "intensity", 0)
        self.assertEqual(fids, (1, 2), "Besitzer stehen in Auswahlreihenfolge")
        self.assertNotEqual(erster, zweiter,
                            "beide Kanaele heissen gleich — dann misst der Test "
                            "die Reihenfolge nicht")
        self.assertEqual(auf, f"{erster}{_SUFFIX}1")


if __name__ == "__main__":
    unittest.main()
