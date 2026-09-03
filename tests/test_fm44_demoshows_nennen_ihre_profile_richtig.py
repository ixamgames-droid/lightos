"""FM-44 — die committeten Demo-Shows muessen ihre Geraete richtig benennen.

Eine Show speichert die Profil-Referenz doppelt: als **SQLite-Auto-ID** und
denormalisiert als **(Herstellername, Modellname)**. Die ID ist rechnerabhaengig
— eine frisch aufgebaute Bibliothek vergibt andere Nummern. Der Name ist der
Rettungsanker, der ueber Rechner hinweg traegt (`show_file._resolve_fixture_profile_id`).

**Ist der Name falsch, ist der Anker weg** — und dann entscheidet die alte ID,
was am Rig steht. Genau das lag latent in `shows/Demo_ZQ_Buehne.lshow`: der
Builder schrieb `manufacturer_name='U King'`, das Profil ist aber unter
`Generic` registriert (beide Seed-Stellen in `fixture_db.py` sind sich darin
einig, die Show war die Ausnahme). Solange die ID zufaellig passte, fiel es
nicht auf; auf einem fremden Rechner waere es FM-43s Fall C geworden — still
das falsche Geraet.

Geprueft wird gegen eine **frisch aus dem Quelltext geseedete** Bibliothek, nicht
gegen `~/.local/share/LightOS/fixtures.db`: nur so misst der Test die Quelle und
nicht den gewachsenen Stand dieses einen Rechners (dieselbe Begruendung wie in
`tests/_fixture_quelle.py`).

★ Die committeten Shows sind die richtige Stelle fuer diesen Waechter: sie sind
die einzigen, die ALLE teilen, und sie referenzieren ausschliesslich
mitgelieferte Geraete — ein Namensfehler darin trifft jeden.
"""
import io
import json
import os
import subprocess
import unittest
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session
from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _committete_shows() -> list[str]:
    """Die von git verfolgten `.lshow`-Dateien — nicht das Verzeichnis auflisten.

    `shows/*.lshow` ist gitignored; verfolgt sind nur die ausdruecklich
    aufgenommenen Demo-Shows. Wer hier `os.listdir` nimmt, prueft auf einem
    benutzten Rechner die privaten Shows mit und wird zufaellig rot.
    """
    aus = subprocess.run(["git", "ls-files", "shows/"], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [z for z in aus.splitlines() if z.endswith(".lshow")]


def _patch_eintraege(pfad: str) -> list[dict]:
    with zipfile.ZipFile(os.path.join(_ROOT, pfad)) as z:
        daten = json.loads(z.read("show.json").decode("utf-8"))
    return list(daten.get("patch") or [])


class DemoShowsNennenIhreProfileTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)
        cls._shows = _committete_shows()

    def _bibliothek(self):
        """``{(hersteller, modell): profil_id}`` der frischen Bibliothek."""
        from src.core.database.models import FixtureProfile, Manufacturer
        with Session(self._eng) as s:
            zeilen = s.execute(
                select(Manufacturer.name, FixtureProfile.name, FixtureProfile.id)
                .join(FixtureProfile,
                      FixtureProfile.manufacturer_id == Manufacturer.id)).all()
        return {(m, f): i for m, f, i in zeilen}

    def test_es_gibt_ueberhaupt_committete_shows(self):
        """Ohne diese Vorbedingung waere der Waechter darunter leer gruen — die
        teuerste Sorte Test."""
        self.assertGreaterEqual(len(self._shows), 3,
                                f"nur {len(self._shows)} verfolgte Shows gefunden")

    def test_jedes_geraet_ist_ueber_seinen_NAMEN_auffindbar(self):
        """Der Kern: (Hersteller, Modell) muss in der frischen Bibliothek
        existieren. Die ID darf abweichen — dafuer gibt es den Anker."""
        bib = self._bibliothek()
        fehler = []
        for show in self._shows:
            for f in _patch_eintraege(show):
                mfr = f.get("manufacturer_name") or ""
                name = f.get("fixture_name") or ""
                if not name:
                    continue          # Alt-Format ohne Namen: nicht Gegenstand
                if (mfr, name) not in bib:
                    treffer = [m for (m, n) in bib if n == name]
                    fehler.append(
                        f"{show}: „{mfr} / {name}“ steht nicht in der Bibliothek"
                        + (f" — das Modell gibt es dort unter {treffer}"
                           if treffer else " (auch das Modell nicht)"))
        self.assertEqual(fehler, [], "\n".join(fehler))

    def test_kein_geraet_ohne_namen(self):
        """Ein Eintrag ohne Modellnamen hat gar keinen Anker — auf einem fremden
        Rechner entscheidet dann allein die ID. In den mitgelieferten Shows darf
        das nicht vorkommen."""
        ohne = [f"{show}: fid {f.get('fid')}"
                for show in self._shows
                for f in _patch_eintraege(show)
                if not (f.get("fixture_name") or "")]
        self.assertEqual(ohne, [], "\n".join(ohne))

    def test_der_zq_buehnen_fall_bleibt_behoben(self):
        """Die konkrete Regression: das PAR der ZQ-Demo gehoert zu `Generic`.

        Bewusst als eigener Test neben der allgemeinen Pruefung — die allgemeine
        wuerde auch gruen, wenn jemand die Show ganz entfernt."""
        eintraege = _patch_eintraege("shows/Demo_ZQ_Buehne.lshow")
        pars = [f for f in eintraege
                if f.get("fixture_name") == "Stage Light ZQ01424"]
        self.assertTrue(pars, "die ZQ-Demo hat keine ZQ01424 mehr")
        for f in pars:
            self.assertEqual(f.get("manufacturer_name"), "Generic")


class BuilderVerdrahtetKeineIdsTest(unittest.TestCase):
    """Die zweite Haelfte von FM-44: der Builder hatte die Profil-IDs als Zahlen
    im Quelltext (17/18). In einer frischen Bibliothek sind es andere — die
    gebaute Show zeigte also auf fremde Profile, sobald jemand sie woanders
    oeffnete. Ein Test am Ergebnis kann das nicht sehen (auf DIESEM Rechner
    stimmten die Zahlen), also wird die Quelle geprueft."""

    def test_der_zq_builder_holt_seine_profile_ueber_den_kurznamen(self):
        quelle = io.open(os.path.join(_ROOT, "tools", "build_demo_zq_show.py"),
                         encoding="utf-8").read()
        self.assertIn('_profil_id("ZQ01424")', quelle)
        self.assertIn('_profil_id("ZQ02001")', quelle)
        self.assertNotIn("PAR_PROFILE, PAR_MODE = 17", quelle,
                         "die hart verdrahtete Profil-ID ist zurueck")


if __name__ == "__main__":
    unittest.main()
