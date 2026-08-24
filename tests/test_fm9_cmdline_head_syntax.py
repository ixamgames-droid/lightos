"""FM-9/A8 — getippte Kopf-Syntax in der Kommandozeile (``1:2 @ 50``).

A7 hat die Kommandozeile an den Auswahl-Vertrag gebunden: sie *respektiert*
seither eine geklickte Kopf-Auswahl. Was fehlte, war der umgekehrte Weg — den
Kopf **selbst benennen**. Gemessen vor dieser Runde::

    '1:2 @ 50'  -> ErrorCommand("Unbekannter Befehl: '1:2 @ 50'.")

Der Lexer brach Worte nur an ``+ - @`` und Leerzeichen, ``1:2`` wurde also ein
einziges Wort-Token und fiel als unbekanntes Keyword durch die ganze Grammatik.

Diese Datei prueft drei Dinge, und die letzten beiden sind der eigentliche Grund
fuer ihre Laenge:

1. **Dass es geht** — Auswahl, Wert, Attribut-Pfad, Zaehlung ab ``K1``.
2. **Dass ein Fehlgriff auffliegt statt zu wirken.** Eine getippte Kopf-Nummer
   ist eine ausdrueckliche Ansage. Fiele ``1:3 @ 100`` bei einem Tippfehler
   still auf geraeteweit zurueck (so wie die *geklickte* Auswahl es darf),
   stuende die volle Intensitaet auf ALLEN Koepfen — sichtbar auf der Buehne.
   Die Kopfzahl haengt dabei am **Attribut**, nicht am Geraet (FM-9/A6).
3. **Dass keine Zelle STILL verschwindet.** Drei Stellen der Grammatik haetten
   eine Kopf-Zelle kommentarlos geschluckt oder — beim Minus — sogar in ihr
   Gegenteil verkehrt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.cmdline.lexer import TokenType, tokenize      # noqa: E402
from src.core.cmdline.parser import parse                   # noqa: E402


class LexerTests(unittest.TestCase):
    def test_kopf_zelle_wird_ein_eigenes_token(self):
        typen = [t.type for t in tokenize("1:2 @ 50")]
        self.assertEqual(typen[0], TokenType.CELL,
                         "vor A8 war '1:2' ein KEYWORD und damit unbrauchbar")

    def test_doppelpunkt_bleibt_sonst_ein_gewoehnliches_zeichen(self):
        """Bewusst kein ``:``-Operator: sonst zerfiele jeder Name mit
        Doppelpunkt (Szenen, Cues) in drei Tokens."""
        toks = tokenize("teil:zwei")
        self.assertEqual(toks[0].type, TokenType.KEYWORD)
        self.assertEqual(toks[0].value, "teil:zwei")
        self.assertEqual(tokenize("1:2:3")[0].type, TokenType.KEYWORD)

    def test_szenen_name_der_wie_eine_zelle_aussieht_bleibt_der_name(self):
        cmd = parse("record scene 1:2")
        self.assertEqual(getattr(cmd, "name", None), "1:2",
                         "sonst hiesse die Szene still 'Neue Szene'")


class GrammatikGuardTests(unittest.TestCase):
    """Die drei Stellen, an denen eine Kopf-Zelle still verschwunden waere."""

    def test_minus_kehrte_sich_sonst_um(self):
        """``consume_number()`` liefert bei einer Zelle ``None`` — die Zelle
        blieb stehen und der naechste Schleifendurchlauf haette sie ADDIERT."""
        res = parse("1 thru 4 - 2:1").execute(_FakePatch([1, 2, 3, 4]))
        self.assertFalse(res.ok)
        self.assertIn("abziehen", res.message)

    def test_all_und_kopf_ziel_widersprechen_sich(self):
        res = parse("all 1:2 @ 50").execute(_FakePatch([1, 2]))
        self.assertFalse(res.ok, "sonst waeren ALLE Geraete voll aufgezogen")

    def test_thru_geht_nicht_ueber_koepfe(self):
        res = parse("1:2 thru 4").execute(_FakePatch([1, 2, 3, 4]))
        self.assertFalse(res.ok)
        self.assertIn("thru", res.message)

    def test_kopf_null_wird_abgewiesen(self):
        """Getippt wird 1-basiert (K1 = erster Kopf) — ``1:0`` ist der Versuch,
        den internen 0-basierten Zellindex zu tippen."""
        res = parse("1:0 @ 50").execute(_FakePatch([1]))
        self.assertFalse(res.ok)
        self.assertIn("1-basiert", res.message)


class _FakePatch:
    """Minimal-State (wie Werkzeuge/Bestandstests ihn fahren) — ohne Library,
    also ohne Kopfzahl-Wissen."""

    def __init__(self, fids):
        self._fids = list(fids)
        self.selected_fids = []
        self.writes = []

    def get_patched_fixtures(self):
        return [type("F", (), {"fid": f})() for f in self._fids]

    def set_programmer_value(self, fid, attribute, value, undoable=False, head=0):
        self.writes.append((fid, attribute if not head else
                            f"{attribute}#{int(head)}", value))


class MinimalStateTests(unittest.TestCase):
    def test_ohne_library_wird_der_getippte_kopf_geschrieben(self):
        """Ein State ohne ``validate_head_restrictions`` kann nichts pruefen —
        dann gilt die Ansage des Nutzers, nicht ein stiller Rueckfall."""
        st = _FakePatch([1, 2])
        res = parse("1:2 @ 100").execute(st)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(st.writes, [(1, "intensity#1", 255)])


class EchterAppStateTests(unittest.TestCase):
    """★ Gegen den ECHTEN AppState samt Library — nur dort gibt es eine
    Kopfzahl, und nur dort faellt ein Fehlgriff ueberhaupt auf."""

    def setUp(self):
        from src.core.app_state import get_state
        from src.core.database import fixture_db
        from src.core.database.models import PatchedFixture
        self.st = get_state()
        prof = next(iter(fixture_db.search_fixtures("HYDRABEAM 4000 RGBW")))
        mode = next(m for m in fixture_db.get_modes(prof.id)
                    if m.name.startswith("19-Kanal"))
        for fid in (1, 2):
            self.st.add_fixture(
                PatchedFixture(fid=fid, label=f"HB{fid}",
                               fixture_profile_id=prof.id, mode_name=mode.name,
                               universe=1, address=1 + (fid - 1) * 19,
                               channel_count=19),
                undoable=False)
        self.st.programmer.clear()
        self.st.set_selected_cells([])

    # ── 1. Dass es geht ────────────────────────────────────────────────────
    def test_getippter_kopf_schreibt_nur_diesen_kopf(self):
        self.assertTrue(parse("1:2 pan 128").execute(self.st).ok)
        self.assertEqual(sorted(self.st.programmer.get(1, {})), ["pan#1"],
                         "K2 ist der Kopf mit Index 1 — jede Oberflaeche "
                         "beschriftet ihn als K2 (f'K{head+1}')")

    def test_erster_kopf_heisst_eins(self):
        self.assertTrue(parse("1:1 pan 10").execute(self.st).ok)
        self.assertEqual(sorted(self.st.programmer.get(1, {})), ["pan"],
                         "Kopf 1 ist der Basis-Schluessel ohne '#'")

    def test_kopf_ziel_setzt_die_feine_auswahl(self):
        parse("1:2").execute(self.st)
        self.assertEqual(self.st.get_selected_cells(), ["1:1"])
        self.assertEqual(self.st.get_selected_fids(), [1],
                         "die fid-Liste bleibt der unveraenderte Vertrag fuer "
                         "alle Konsumenten (SELECTION_CHANGED)")

    def test_auswahl_meldet_den_kopf_so_wie_er_getippt_wurde(self):
        res = parse("1:2").execute(self.st)
        self.assertIn("1·K2", res.message)

    def test_gemischt_ganzes_geraet_und_kopf(self):
        parse("2 + 1:2").execute(self.st)
        self.assertEqual(sorted(self.st.get_selected_cells()), ["1:1", "2"])

    def test_ganzes_geraet_schlaegt_seinen_eigenen_kopf(self):
        """``1 + 1:2`` nennt das ganze Geraet — dieselbe Vorrang-Regel wie in
        ``set_selected_cells``/``head_restrictions`` (die groebere Aussage)."""
        parse("1 + 1:2 pan 77").execute(self.st)
        self.assertEqual(sorted(self.st.programmer.get(1, {})), ["pan"])

    def test_alle_koepfe_genannt_ist_das_ganze_geraet(self):
        """Vier Pan-Koepfe, alle vier getippt -> geraeteweit schreiben (sonst
        verloere ein geteilter Master-Dimmer seinen Wert, s. A4)."""
        self.assertTrue(
            parse("1:1 + 1:2 + 1:3 + 1:4 pan 99").execute(self.st).ok)
        self.assertEqual(sorted(self.st.programmer.get(1, {})), ["pan"])

    # ── 2. Dass ein Fehlgriff auffliegt ────────────────────────────────────
    def test_kopf_den_es_fuer_dieses_attribut_nicht_gibt_wird_gemeldet(self):
        """★ Der Kern: dieselbe HYDRABEAM hat 4 Pan-, aber nur EINE Farbbank.
        ``1:2 red 200`` erzeugte sonst ``color_r#1`` — einen Schluessel, den
        ``_flush_programmer_to_dmx`` nie liest, der Kopf faellt auf seinen
        ``default_value`` (A5, an echten Kanaelen gemessen)."""
        res = parse("1:2 red 200").execute(self.st)
        self.assertFalse(res.ok, "ein stiller Rueckfall auf geraeteweit haette "
                                 "ALLE Koepfe rot gefaerbt")
        self.assertIn("nur einen Kopf", res.message)
        self.assertEqual(self.st.programmer.get(1, {}), {},
                         "und geschrieben werden darf dabei gar nichts")

    def test_zu_grosse_kopfnummer_wird_gemeldet(self):
        res = parse("1:9 pan 128").execute(self.st)
        self.assertFalse(res.ok)
        self.assertIn("4 Köpfe", res.message)
        self.assertEqual(self.st.programmer.get(1, {}), {})

    def test_dieselbe_zelle_ist_je_nach_attribut_gueltig_oder_nicht(self):
        """Die Zaehlung folgt dem Attribut: 4 Pan, 4 Tilt, 1 Farbbank."""
        self.assertTrue(parse("1:4 pan 20").execute(self.st).ok)
        self.assertTrue(parse("1:4 tilt 20").execute(self.st).ok)
        self.assertFalse(parse("1:5 pan 20").execute(self.st).ok,
                         "Pan hat nur 4")

    def test_geteilter_master_wird_aufgeloest_statt_abgewiesen(self):
        """★★ Zonen-Master-Falle, an der echten Library gemessen — und seit
        FM-29 (2026-08-24) **aufgeloest** statt abgewiesen.

        Die HYDRABEAM 4000 RGBW [19-Kanal] legt ihre **5** Intensity-Kanaele so
        an::

            CH1  Master Dimmer      <- gemeinsam
            CH9  Kopf 1 Dimmer
            CH12 Kopf 2 Dimmer
            CH15 Kopf 3 Dimmer
            CH18 Kopf 4 Dimmer

        Solange ``attr_head_count_for_channels`` die VORKOMMEN zaehlte, standen
        hier „5 Kanaele" gegen „4 Koepfe" — ein Widerspruch, den die
        Kommandozeile lieber meldete als riet (``1:2 @ 50`` waere sonst
        ``intensity#1`` = CH9 = „Kopf 1 Dimmer" gewesen, ein Kopf daneben).
        Seit FM-29 antwortet die Zaehlung mit der Kopf-KARTE aus FM-17: 4
        Koepfe, kein Widerspruch mehr — und dieselbe Karte sagt auch, welcher
        Kanal K2 gehoert.

        Gemessen wird deshalb der AUSGANG auf DMX, nicht die Erfolgsmeldung."""
        from src.core.app_state import get_channels_for_patched
        fx = next(f for f in self.st.get_patched_fixtures() if f.fid == 1)
        uni = self.st.universes[fx.universe]

        def dmx_jetzt():
            return {c.name: uni.get_channel(fx.address + c.channel_number - 1)
                    for c in get_channels_for_patched(fx)}

        # Die Show wird zwischen den Testmethoden nicht geleert — Ausgangslage
        # ausdruecklich pruefen, sonst koennte ein Restwert das Ergebnis
        # vortaeuschen.
        vorher = dmx_jetzt()
        for name in ("Master Dimmer", "Kopf 1 Dimmer", "Kopf 2 Dimmer",
                     "Kopf 3 Dimmer", "Kopf 4 Dimmer"):
            self.assertEqual(vorher[name], 0, f"{name} war schon gesetzt")
        res = parse("1:2 @ 50").execute(self.st)
        self.assertTrue(res.ok, res.message)
        dmx = dmx_jetzt()
        self.assertEqual(dmx["Kopf 2 Dimmer"], 128, "K2 = CH12, nicht CH9")
        self.assertEqual(dmx["Master Dimmer"], 128,
                         "der geteilte Master kommt ueber FM-17 mit — sonst "
                         "bliebe der richtig adressierte Kopf dunkel")
        for anderer in ("Kopf 1 Dimmer", "Kopf 3 Dimmer", "Kopf 4 Dimmer"):
            self.assertEqual(dmx[anderer], 0,
                             f"{anderer} darf nicht mitziehen")

    def test_echter_widerspruch_wird_weiter_gemeldet(self):
        """★ Positivkontrolle zum Test darueber: die Verweigerung ist NICHT
        abgeschafft, sie greift nur nicht mehr dort, wo die Kopf-Karte die
        Zuordnung kennt.

        Ueber die eingebauten Profile ausgezaehlt bleibt genau ein Fall uebrig:
        ``ZQ06121 [154-Kanal 48 Zonen RGB + 8x Weiss]`` — 48 Farbzonen, aber nur
        **8** Weiss-Kanaele. Welcher davon zu „K2" gehoert, ist nicht
        entscheidbar, also wird nicht geraten."""
        from src.core.app_state import get_channels_for_patched
        from src.core.database import fixture_db
        from src.core.database.models import PatchedFixture
        prof = next(p for p in fixture_db.search_fixtures("")
                    if p.short_name == "ZQ06121")
        mode = next(m for m in fixture_db.get_modes(prof.id)
                    if m.channel_count == 154)
        # ★ Freie fid/Adresse suchen statt „3" zu tippen: ``setUp`` laeuft je
        # Testmethode und die Show wird zwischen den Methoden NICHT geleert —
        # ein belegtes fid wird beim Patchen still weitergezaehlt, und der Test
        # haette dann eine Hydrabeam gemessen statt des Zonen-Panels.
        vorhanden = list(self.st.get_patched_fixtures())
        fid = max((int(f.fid) for f in vorhanden), default=0) + 1
        adr = max((int(f.address) + int(f.channel_count) for f in vorhanden
                   if int(f.universe) == 1), default=1)
        self.st.add_fixture(
            PatchedFixture(fid=fid, label="Zone", fixture_profile_id=prof.id,
                           mode_name=mode.name, universe=1, address=adr,
                           channel_count=154), undoable=False)
        fx = next(f for f in self.st.get_patched_fixtures() if f.fid == fid)
        self.assertEqual(
            sum(1 for c in get_channels_for_patched(fx)
                if (c.attribute or "") == "color_w"), 8,
            "das gepatchte Geraet muss wirklich das Zonen-Panel sein")
        res = parse(f"{fid}:2 white 50").execute(self.st)
        self.assertFalse(res.ok, "48 Zonen gegen 8 Weiss-Kanaele — hier gibt es "
                                 "keine richtige Antwort zu raten")
        self.assertIn("nicht eindeutig", res.message)
        self.assertEqual(self.st.programmer.get(fid, {}), {})

    def test_fehlender_beleg_ist_kein_widerspruch(self):
        """Ohne Pan/Farb-Beleg (reiner Dimmer-Balken, 338 Modi der Library)
        bleibt die Kopfzahl des Attributs die einzige Aussage — dann wird
        NICHT abgewiesen."""
        from src.core.cmdline.parser import _geraet_kopfzahl
        chans = [type("C", (), {"attribute": "intensity"})() for _ in range(4)]
        null = lambda _fx, _ch: 1                                  # noqa: E731
        self.assertEqual(_geraet_kopfzahl(None, chans, null, null), 1,
                         "1 = kein Beleg -> die Gegenprobe greift gar nicht")

    # ── 3. Dass der Bestandspfad unveraendert bleibt ───────────────────────
    def test_ohne_kopf_ziel_bleibt_alles_wie_vorher(self):
        res = parse("1 thru 2 @ 50").execute(self.st)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(sorted(self.st.programmer.get(1, {})), ["intensity"])
        self.assertEqual(self.st.get_selected_cells(), [],
                         "ein reiner Wert-Befehl aendert die Auswahl nicht")

    def test_geklickte_auswahl_wirkt_weiter_wie_in_a7(self):
        self.st.set_selected_cells(["2:1"])
        self.assertTrue(parse("pan 128").execute(self.st).ok)
        self.assertEqual(sorted(self.st.programmer.get(2, {})), ["pan#1"])


if __name__ == "__main__":
    unittest.main()
