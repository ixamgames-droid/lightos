"""FM-43 — ein fehlendes Geraeteprofil darf nicht stumm verschwinden.

`_resolve_fixture_profile_id` (src/core/show/show_file.py) haelt die Show-Referenz
ueber Rechner hinweg stabil: passt die gespeicherte SQLite-ID nicht mehr, wird
ueber Hersteller + Modellname nachgeschlagen. Findet auch das nichts, endete die
Funktion bis zum 03.09.2026 **stumm** mit der alten ID — und was diese ID dann
trifft, entscheidet, wie schlimm es wird.

Gemessen am 02.09.2026 auf einer Bibliothek ohne die Profile: **6 von 6 Geraeten
loesen null Kanaele auf**, die Show meldet „geladen", `tools/lint_show.py` meldet
„0 Fehler", und am Rig bleibt es dunkel. Der schlimmere Ausgang war noch stiller:
zeigt die alte ID auf ein ANDERES Profil, faehrt dieses — gemessen lief ein
11-Kanal-Eintrag als 4-Kanal-PAR.

Diese Datei nagelt die drei Ausgaenge einzeln fest, dazu die zweite Haelfte des
Items: die Mehrdeutigkeit wird nicht mehr von der Einfuegereihenfolge entschieden.

★ Bewusst NICHT gemessen wird hier eine Textformulierung um ihrer selbst willen —
geprueft wird jeweils die AUSSAGE (bleibt dunkel / es faehrt ein anderes Geraet /
es gibt eine Dublette). Ein Test, der nur auf einen Satz greppt, geht beim naechsten
Umformulieren kaputt, ohne dass sich das Verhalten geaendert haette.
"""
import os
import unittest

from sqlalchemy import select
from sqlalchemy.orm import Session
from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FEHLT_MFR = "Phantom GmbH"
FEHLT_NAME = "Gibt Es Nicht 9000"


def _profil(session, pid):
    from src.core.database.models import FixtureProfile
    return session.execute(
        select(FixtureProfile).where(FixtureProfile.id == pid)).scalar_one_or_none()


class _Basis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)

    def setUp(self):
        from src.core.show import show_file as SF
        self.SF = SF
        SF._ladeprobleme.clear()
        self.addCleanup(SF._ladeprobleme.clear)

    def _loesen(self, pid, mfr, name):
        return self.SF._resolve_fixture_profile_id(pid, mfr, name)

    @property
    def meldungen(self):
        return list(self.SF._ladeprobleme)

    def _eine_meldung(self):
        self.assertEqual(len(self.meldungen), 1,
                         f"genau eine Meldung erwartet, war: {self.meldungen}")
        return self.meldungen[0]


class TrefferBleibtStillTest(_Basis):
    """Der Normalfall darf NICHT lauter werden — sonst ist die Warnung wertlos."""

    def test_passende_id_meldet_nichts(self):
        with Session(self._eng) as s:
            p = _profil(s, 1)
            mfr = p.manufacturer.name
            name = p.name
        self.assertEqual(self._loesen(1, mfr, name), 1)
        self.assertEqual(self.meldungen, [])

    def test_remap_ueber_den_namen_meldet_nichts(self):
        """Der Rettungsanker greift — das ist Erfolg, keine Warnung. Er druckt
        wie bisher eine Zeile auf stdout, aber er belaestigt den Nutzer nicht."""
        with Session(self._eng) as s:
            p = _profil(s, 3)
            mfr, name = p.manufacturer.name, p.name
        self.assertEqual(self._loesen(999999, mfr, name), 3)
        self.assertEqual(self.meldungen, [])

    def test_alt_show_ohne_modellnamen_bleibt_unveraendert(self):
        """Legacy-Shows ohne `fixture_name` gehen oben raus, bevor irgendetwas
        nachgeschlagen wird. Sie duerfen keine Warnung erzeugen — sonst meldet
        LightOS bei jeder alten Show etwas, das niemand beheben kann."""
        self.assertEqual(self._loesen(4711, "", ""), 4711)
        self.assertEqual(self.meldungen, [])


class FehlendesProfilTest(_Basis):

    def test_id_zeigt_ins_leere__geraet_bleibt_dunkel(self):
        """Ausgang B: die ID trifft nichts. Das Geraet hat danach keine Kanaele —
        genau der Zustand, den RIG-DUNKEL beschreibt."""
        self.assertEqual(self._loesen(999999, FEHLT_MFR, FEHLT_NAME), 999999,
                         "die ID darf sich nicht aendern, nur die Stille")
        m = self._eine_meldung()
        self.assertIn(FEHLT_NAME, m, "die Meldung nennt das gesuchte Geraet nicht")
        self.assertIn("DUNKEL", m,
                      "die Folge muss dastehen, nicht nur die Ursache")

    def test_id_zeigt_auf_fremdes_profil__das_falsche_geraet_faehrt(self):
        """Ausgang C, der gefaehrlichste: die ID trifft ein ANDERES Geraet, und
        genau das wird angesteuert. Die Meldung muss das fremde Geraet BENENNEN —
        ohne den Namen sucht der Mensch den Fehler in der Show."""
        with Session(self._eng) as s:
            fremd = _profil(s, 2)
            fremd_name = fremd.name
        self.assertEqual(self._loesen(2, FEHLT_MFR, FEHLT_NAME), 2)
        m = self._eine_meldung()
        self.assertIn(FEHLT_NAME, m)
        self.assertIn(fremd_name, m,
                      "das fremde Geraet muss beim Namen genannt sein")

    def test_die_beiden_faelle_sind_unterscheidbar(self):
        """★ Der Kern des Items: bis 03.09. war 'dunkel' von 'falsches Geraet'
        nicht zu unterscheiden — beide waren stumm. Zwei gleiche Meldungen waeren
        derselbe Fehler eine Ebene hoeher."""
        self._loesen(999999, FEHLT_MFR, FEHLT_NAME)
        leer = self._eine_meldung()
        self.SF._ladeprobleme.clear()
        self._loesen(2, FEHLT_MFR, FEHLT_NAME)
        fremd = self._eine_meldung()
        self.assertNotEqual(leer, fremd)

    def test_die_meldung_erreicht_die_oberflaeche(self):
        """Der Sammler ist nur die halbe Miete — die UI liest
        `letzte_ladeprobleme()`, und daran haengt der Warndialog (QA-50)."""
        self._loesen(999999, FEHLT_MFR, FEHLT_NAME)
        self.assertEqual(self.SF.letzte_ladeprobleme(), self.meldungen)
        self.assertTrue(self.SF.letzte_ladeprobleme())


class MehrdeutigkeitTest(_Basis):
    """Die zweite Haelfte des Items: bei mehreren Treffern entschied bisher
    `order_by(id).first()` — also die Einfuegereihenfolge, und damit systematisch
    der aeltere Import statt des gepflegten Builtins."""

    _lauf = 0

    def _dublette_anlegen(self, builtin_zuerst: bool):
        """Legt dasselbe (Hersteller, Modell) zweimal an — einmal `builtin`,
        einmal `qlcplus` — in der gewuenschten Einfuegereihenfolge und gibt
        ``(builtin_id, fremd_id, mfr, name)`` zurueck.

        ★ Modellname pro Aufruf verschieden: die Library gehoert der KLASSE
        (`setUpClass`), nicht dem einzelnen Test. Ein fester Name liesse den
        zweiten Test auf den Zwillingen des ersten arbeiten — und dann prueft er
        etwas anderes, als er behauptet."""
        from src.core.database.models import FixtureProfile, Manufacturer
        MehrdeutigkeitTest._lauf += 1
        n = MehrdeutigkeitTest._lauf
        name = f"Zwilling {n}"
        with Session(self._eng) as s:
            m = s.execute(select(Manufacturer)
                          .where(Manufacturer.name == "Doppel AG")).scalar_one_or_none()
            if m is None:
                m = Manufacturer(name="Doppel AG", short_name="DOPP")
                s.add(m)
                s.flush()
            reihenfolge = (["builtin", "qlcplus"] if builtin_zuerst
                           else ["qlcplus", "builtin"])
            ids = {}
            for quelle in reihenfolge:
                p = FixtureProfile(manufacturer=m, name=name,
                                   short_name=f"ZW{n}{quelle[:3].upper()}",
                                   fixture_type="par", power_w=10, source=quelle)
                s.add(p)
                s.flush()
                ids[quelle] = p.id
            s.commit()
            return ids["builtin"], ids["qlcplus"], "Doppel AG", name

    def test_builtin_gewinnt__auch_wenn_es_spaeter_eingefuegt_wurde(self):
        """Der gemessene Fall aus der echten Bibliothek: der QLC+-Import hat die
        kleinere ID, das gepflegte Builtin die groessere — und bisher gewann die
        kleinere. Bei einer Kollision unterschied sich sogar der `fixture_type`
        (`led_bar` gegen `matrix`): anderes 3D-Modell, anderer Renderpfad."""
        b_id, q_id, mfr, name = self._dublette_anlegen(builtin_zuerst=False)
        self.assertGreater(b_id, q_id, "Vorbedingung: Builtin hat die groessere ID")
        self.assertEqual(self._loesen(999999, mfr, name), b_id,
                         "das gepflegte Builtin muss gewinnen, nicht der aeltere Import")

    def test_die_wahl_haengt_nicht_an_der_einfuegereihenfolge(self):
        """Derselbe Inhalt, BEIDE Reihenfolgen, jeweils das Builtin — sonst
        entscheidet der Zufall der Bibliothek, welches Geraet am Rig steht.

        ★ Diese Fassung ist von der Mutationsmessung erzwungen. Die erste
        pruefte nur `builtin_zuerst=True` — dort hat das Builtin ohnehin die
        kleinere ID, also waehlt die ALTE Regel (`order_by(id)`) dasselbe. Der
        Test blieb bei der Mutation gruen und hat damit nichts gemessen. Erst
        das Paar aus beiden Reihenfolgen trennt die zwei Regeln."""
        b_frueh, q_frueh, mfr, name_frueh = self._dublette_anlegen(builtin_zuerst=True)
        b_spaet, q_spaet, _mfr, name_spaet = self._dublette_anlegen(builtin_zuerst=False)
        self.assertLess(b_frueh, q_frueh, "Vorbedingung: hier ist das Builtin aelter")
        self.assertGreater(b_spaet, q_spaet, "Vorbedingung: hier ist das Builtin juenger")
        self.assertEqual(self._loesen(999999, mfr, name_frueh), b_frueh)
        self.SF._ladeprobleme.clear()
        self.assertEqual(self._loesen(999999, mfr, name_spaet), b_spaet,
                         "die Einfuegereihenfolge darf die Wahl nicht drehen")

    def test_die_dublette_wird_gemeldet(self):
        """Ein Geraet, das *fast* stimmt, schickt den Menschen auf die falsche
        Suche. Die Meldung sagt, dass es die Bibliothek ist und nicht die Show."""
        _b, _q, mfr, name = self._dublette_anlegen(builtin_zuerst=False)
        self._loesen(999999, mfr, name)
        m = self._eine_meldung()
        self.assertIn(name, m)
        self.assertIn("2", m, "die Anzahl der Treffer gehoert in die Meldung")

    def test_ein_eindeutiger_treffer_meldet_nichts(self):
        """Positivkontrolle zur Dubletten-Meldung: ohne Zwilling bleibt es still."""
        with Session(self._eng) as s:
            p = _profil(s, 3)
            mfr, name = p.manufacturer.name, p.name
        self._loesen(999999, mfr, name)
        self.assertEqual(self.meldungen, [])


if __name__ == "__main__":
    unittest.main()
