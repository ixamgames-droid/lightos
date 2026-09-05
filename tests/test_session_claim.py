"""PROC-01 — der Belegzettel fuer parallele Sitzungen muss ein Rennen entscheiden.

★ Der Punkt dieses Werkzeugs ist **nicht**, dass es eine Markdown-Tabelle
pflegt — das koennte man von Hand. Der Punkt ist, dass zwei Sitzungen, die im
selben Moment dasselbe Item nehmen wollen, hinterher **wissen**, wer es hat.
Genau das kann eine Pruefung allein nicht leisten: beide lesen „frei".

Entschieden wird es erst am Push. Deshalb testet die zentrale Klasse hier
gegen ein **echtes Bare-Repo** mit **zwei echten Klonen** — eine Attrappe
koennte den Fall gar nicht zeigen, weil sie das Fast-Forward-Verhalten von Git
nachbauen muesste, also genau das, was hier bewiesen werden soll.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import session_claim as sc      # noqa: E402


def _git(*args, repo=None, eingabe=None):
    r = subprocess.run(["git", *args], cwd=repo, input=eingabe,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)}: {r.stderr}"
    return r.stdout.strip()


class TafelFormatTest(unittest.TestCase):
    """Lesen und Schreiben muessen sich gegenseitig ueberleben."""

    def test_rundreise(self):
        tafel = {
            "claims": [{"item": "OUT-51", "sitzung": "B",
                        "branch": "fix/out51", "seit": "2026-08-06T14:10Z",
                        "dateien": "src/core/dmx/output_manager.py"}],
            "blocker": ["2026-08-06T14:00Z (A) Rig ist in Benutzung"],
            "verlauf": ["2026-08-06T14:10Z B claim OUT-51"],
        }
        wieder = sc.parse(sc.rendere(tafel))
        self.assertEqual(wieder["claims"], tafel["claims"])
        self.assertEqual(wieder["blocker"], tafel["blocker"])
        self.assertEqual(wieder["verlauf"], tafel["verlauf"])

    def test_leere_tafel_ist_lesbar(self):
        leer = sc.parse(sc.rendere(sc.parse("")))
        self.assertEqual(leer["claims"], [])

    def test_kaputte_zeile_macht_die_tafel_nicht_unlesbar(self):
        # Eine von Hand verhunzte Zeile darf nicht die Koordination ALLER
        # Sitzungen ausfallen lassen.
        inhalt = sc.rendere({"claims": [
            {"item": "OUT-51", "sitzung": "B", "branch": "x",
             "seit": "2026-08-06T14:10Z", "dateien": "-"}],
            "blocker": [], "verlauf": []})
        inhalt += "| kaputt\n| | | |\n"
        tafel = sc.parse(inhalt)
        self.assertEqual([c["item"] for c in tafel["claims"]], ["OUT-51"])


class VerfallTest(unittest.TestCase):
    def test_frischer_claim_gilt(self):
        t = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
        c = {"seit": sc.stempel(t - timedelta(hours=1))}
        self.assertFalse(sc.ist_verfallen(c, t))

    def test_alter_claim_verfaellt(self):
        t = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
        c = {"seit": sc.stempel(t - timedelta(hours=5))}
        self.assertTrue(sc.ist_verfallen(c, t))

    def test_unlesbarer_stempel_gilt_NICHT_als_verfallen(self):
        """★ Die gefaehrlichere Richtung bewusst gewaehlt.

        Einen Claim, den man nicht datieren kann, im Zweifel zu uebernehmen
        hiesse: zwei Sitzungen am selben Item. Ihn stehen zu lassen kostet
        hoechstens Wartezeit — und die faellt auf, der Doppelgriff nicht.
        """
        t = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
        self.assertFalse(sc.ist_verfallen({"seit": "gestern"}, t))
        self.assertFalse(sc.ist_verfallen({}, t))


# ★ Bewusst zusammengesetzt statt ausgeschrieben. Diese Datei prueft einen
# Waechter, der genau solche Pfade sucht — stuende das Beispiel woertlich hier,
# schlueg `tests/test_keine_privaten_dateien.py` an der Testdatei des eigenen
# Waechters an. (Genau so passiert, 2026-08-06: das Gate fand sich selbst.)
# Die Namen sind erfunden; es geht nur um die FORM des Pfades. Bewusst
# ZUSAMMENGESETZT und nicht hingeschrieben: der Waechter in
# tests/test_keine_privaten_dateien.py durchsucht `tests/` mit, und ein
# Literal hier waere fuer ihn nicht von einem echten Leck zu unterscheiden.
# PRIV-04: bis 2026-09-03 galt das nur fuer die Linux-Zeile — die Windows-Form
# stand als Literal da, weil sie gar nicht geprueft wurde.
_BEISPIEL_HOME = "/home/" + "martin"
_BEISPIEL_WIN = r"C:\Users" + "\\" + "Anna" + r"\lightos kaputt"


class OeffentlichkeitsPruefungTest(unittest.TestCase):
    """Die Tafel liegt auf GitHub — Blocker-Freitext ist die Leck-Stelle."""

    def test_faengt_private_angaben(self):
        self.assertTrue(sc.pruefe_oeffentlich(f"Show liegt in {_BEISPIEL_HOME}/shows"))
        self.assertTrue(sc.pruefe_oeffentlich(_BEISPIEL_WIN))
        self.assertTrue(sc.pruefe_oeffentlich("siehe claude.ai/code/session_abc"))
        self.assertTrue(sc.pruefe_oeffentlich("melde dich bei a.b@example.com"))

    def test_laesst_fachliches_durch(self):
        for text in ("Enttec auf /dev/ttyUSB0 haengt",
                     "Art-Net an 192.168.1.99 antwortet nicht",
                     "test_viz14_place_ghost_scene.py flakt (XPLAT-17)",
                     "Pfade bitte als /home/user/ schreiben"):
            self.assertEqual(sc.pruefe_oeffentlich(text), [], text)


class EchtesRennenTest(unittest.TestCase):
    """★★ Der Test, wegen dem es das Werkzeug gibt.

    Zwei Klone, beide sehen „frei", beide claimen dasselbe Item. Genau einer
    darf gewinnen — und der Verlierer muss es **merken**, nicht in dem Glauben
    weiterarbeiten, er haette das Item.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lightos_claim_")
        self.bare = os.path.join(self.tmp, "origin.git")
        _git("init", "--quiet", "--bare", self.bare)
        self.a = self._klon("a")
        self.b = self._klon("b")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _klon(self, name):
        pfad = os.path.join(self.tmp, name)
        _git("clone", "--quiet", self.bare, pfad)
        _git("config", "user.email", "test@example.invalid", repo=pfad)
        _git("config", "user.name", "Test", repo=pfad)
        return pfad

    def _claim(self, repo, item, sitzung):
        return sc.main(["--repo", repo, "claim", item, "--session", sitzung,
                        "--branch", f"fix/{item.lower()}"])

    def test_genau_einer_gewinnt(self):
        # Beide lesen den (leeren) Stand, bevor einer schreibt — das ist die
        # Gleichzeitigkeit, um die es geht.
        tafel_a, eltern_a = sc.lade_tafel(self.a)
        tafel_b, eltern_b = sc.lade_tafel(self.b)
        self.assertEqual(eltern_a, eltern_b)

        tafel_a["claims"].append({"item": "OUT-51", "sitzung": "A",
                                  "branch": "x", "seit": sc.stempel(sc.jetzt()),
                                  "dateien": "-"})
        tafel_b["claims"].append({"item": "OUT-51", "sitzung": "B",
                                  "branch": "y", "seit": sc.stempel(sc.jetzt()),
                                  "dateien": "-"})

        self.assertTrue(sc.schreibe_tafel(self.a, tafel_a, eltern_a, "A"))
        # ★ B schreibt gegen den Stand, den es GELESEN hat — der ist nicht mehr
        # die Spitze. Git lehnt ab; genau daran erkennt B das verlorene Rennen.
        self.assertFalse(sc.schreibe_tafel(self.b, tafel_b, eltern_b, "B"))

        endstand, _ = sc.lade_tafel(self.b)
        self.assertEqual([c["sitzung"] for c in endstand["claims"]], ["A"])

    def test_verlierer_bekommt_belegt_gemeldet(self):
        self.assertEqual(self._claim(self.a, "OUT-51", "A"), 0)
        # B kennt A's Claim noch nicht — bis `claim` selbst fetcht.
        self.assertEqual(self._claim(self.b, "OUT-51", "B"), 1,
                         "B haette das Item sonst fuer sich reklamiert")
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(len(tafel["claims"]), 1)
        self.assertEqual(tafel["claims"][0]["sitzung"], "A")

    def test_verschiedene_items_stoeren_sich_nicht(self):
        self.assertEqual(self._claim(self.a, "OUT-51", "A"), 0)
        self.assertEqual(self._claim(self.b, "QA-50", "B"), 0)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual({c["item"]: c["sitzung"] for c in tafel["claims"]},
                         {"OUT-51": "A", "QA-50": "B"})

    def test_freigeben_macht_das_item_wieder_belegbar(self):
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(sc.main(["--repo", self.a, "release", "OUT-51",
                                  "--session", "A", "--status", "done"]), 0)
        self.assertEqual(self._claim(self.b, "OUT-51", "B"), 0)

    def test_fremdes_item_nicht_versehentlich_freigeben(self):
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(sc.main(["--repo", self.b, "release", "OUT-51",
                                  "--session", "B"]), 1,
                         "B darf A's Item nicht ohne --force freigeben")

    def test_eigener_claim_laesst_sich_auffrischen(self):
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(sc.main(["--repo", self.a, "refresh", "OUT-51",
                                  "--session", "A"]), 0)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual(len(tafel["claims"]), 1)

    def test_umbelegen_traegt_zweig_und_dateien_nach(self):
        """★★★ PROC-12, GEMESSEN IM ECHTEN BETRIEB: ein erneuter ``claim``
        derselben Sitzung hat nur den Zeitstempel angefasst und ``--branch``
        sowie ``--files`` STILL VERWORFEN — und dabei „Claim aufgefrischt"
        gemeldet, also Erfolg.

        Was daraus wurde: A hat FM-41 zweimal mit neuem Zweig und neuer
        Dateiliste belegt; die Tafel zeigte weiterhin den ERSTEN Zweig und EINE
        Datei. B las daraus, A fasse ``app_state.py`` nicht an, und nahm sich
        ein Item, das genau dort arbeitet. **Die Tafel verschwieg eine
        Ueberschneidung, statt sie zu nennen** — die einzige Fehlrichtung, die
        dieses Werkzeug nicht haben darf, denn es existiert genau dafuer.
        """
        self._claim(self.a, "OUT-51", "A")
        rc = sc.main(["--repo", self.a, "claim", "OUT-51", "--session", "A",
                      "--branch", "feature/zweiter-zweig",
                      "--files", "src/x.py", "src/y.py"])
        self.assertEqual(rc, 0)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual(len(tafel["claims"]), 1, "kein zweiter Eintrag")
        eintrag = tafel["claims"][0]
        self.assertEqual(eintrag["branch"], "feature/zweiter-zweig")
        self.assertIn("src/x.py", eintrag["dateien"])
        self.assertIn("src/y.py", eintrag["dateien"])

    def test_umbelegen_steht_im_verlauf(self):
        """Die andere Sitzung muss die Aenderung SEHEN koennen, nicht nur den
        neuen Endzustand — sonst merkt niemand, dass sich der Zuschnitt
        verschoben hat."""
        self._claim(self.a, "OUT-51", "A")
        sc.main(["--repo", self.a, "claim", "OUT-51", "--session", "A",
                 "--branch", "feature/zweiter-zweig", "--files", "src/x.py"])
        tafel, _ = sc.lade_tafel(self.a)
        verlauf = " ".join(tafel["verlauf"])
        self.assertIn("aktualisiert OUT-51", verlauf)
        self.assertIn("feature/zweiter-zweig", verlauf)

    def test_refresh_bleibt_ein_reines_auffrischen(self):
        """★ Die Gegenprobe, und sie ist der Grund fuer die Bedingung
        ``args.files is not None``: ``refresh`` reicht bewusst ``None`` durch
        und darf den Zuschnitt NICHT loeschen. Ohne diese Abgrenzung haette
        der Fix aus einem stillen Verschweigen ein stilles Vergessen gemacht."""
        sc.main(["--repo", self.a, "claim", "OUT-51", "--session", "A",
                 "--branch", "fix/eins", "--files", "src/x.py"])
        sc.main(["--repo", self.a, "refresh", "OUT-51", "--session", "A"])
        eintrag = sc.lade_tafel(self.a)[0]["claims"][0]
        self.assertEqual(eintrag["branch"], "fix/eins")
        self.assertIn("src/x.py", eintrag["dateien"])

    def test_verfallener_claim_wird_uebernommen_und_protokolliert(self):
        self._claim(self.a, "OUT-51", "A")
        # Claim kuenstlich altern lassen.
        tafel, eltern = sc.lade_tafel(self.a)
        tafel["claims"][0]["seit"] = sc.stempel(sc.jetzt() - timedelta(hours=9))
        sc.schreibe_tafel(self.a, tafel, eltern, "altern")

        self.assertEqual(self._claim(self.b, "OUT-51", "B"), 0)
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(tafel["claims"][0]["sitzung"], "B")
        self.assertTrue(any("uebernimmt OUT-51" in v for v in tafel["verlauf"]),
                        "eine Uebernahme muss nachvollziehbar bleiben")

    def test_blocker_mit_privatem_pfad_wird_abgelehnt(self):
        self.assertEqual(sc.main(["--repo", self.a, "blocker",
                                  f"kaputt: {_BEISPIEL_HOME}/shows/x.lshow",
                                  "--session", "A"]), 2)
        tafel, _ = sc.lade_tafel(self.a)
        self.assertEqual(tafel["blocker"], [])

    def test_blocker_landet_fuer_die_andere_sitzung_sichtbar(self):
        self.assertEqual(sc.main(["--repo", self.a, "blocker",
                                  "Rig laeuft — App nicht neu starten",
                                  "--session", "A"]), 0)
        tafel, _ = sc.lade_tafel(self.b)
        self.assertEqual(len(tafel["blocker"]), 1)
        self.assertIn("Rig laeuft", tafel["blocker"][0])

    def test_arbeitsbaum_bleibt_unberuehrt(self):
        """★ Ein Claim darf der anderen Sitzung nicht in den Worktree greifen.

        Deshalb Plumbing statt Checkout: kein Branch-Wechsel, keine Datei im
        Arbeitsbaum, kein Eingriff in laufende Arbeit.
        """
        _git("commit", "--quiet", "--allow-empty", "-m", "start", repo=self.a)
        vorher_status = _git("status", "--porcelain", repo=self.a)
        vorher_branch = _git("rev-parse", "--abbrev-ref", "HEAD", repo=self.a)
        self._claim(self.a, "OUT-51", "A")
        self.assertEqual(_git("status", "--porcelain", repo=self.a), vorher_status)
        self.assertEqual(_git("rev-parse", "--abbrev-ref", "HEAD", repo=self.a),
                         vorher_branch)
        self.assertFalse(os.path.exists(os.path.join(self.a, sc.DATEI)))


if __name__ == "__main__":
    unittest.main()
