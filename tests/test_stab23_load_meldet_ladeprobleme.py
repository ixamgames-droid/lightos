"""STAB-23: ein Ladefehler im Patch-Block darf nicht als Erfolg durchgehen.

Der Hergang: laeuft eine zweite Instanz (oder ein ``tools/``-Skript) auf
derselben Show-DB und haelt eine Schreib-Transaktion, dann scheitert der
Patch-Austausch mit ``database is locked``. Bis 2026-08-31 wurde das INNERHALB
von ``_replace_patch_from_data`` mit einem blossen ``print`` geschluckt — also
BEVOR der Aufrufer es ueber ``_lenient("load patch error")`` melden konnte.

Folge: ``load_show`` gab ``(True, "Show 'X' geladen.")`` zurueck,
``letzte_ladeprobleme()`` war leer, der Warndialog in
``main_window._open_show_path`` blieb aus — und auf der Buehne stand weiter der
ALTE Patch. **Der Schaden entsteht beim naechsten Speichern:** dann wird der
alte Patch in die gerade geoeffnete Datei geschrieben.

Dieselbe Fehlerklasse wie QA-50 („etwas meldet Erfolg, ohne ihn zu kennen") —
die Meldekette dafuer existierte bereits vollstaendig, sie wurde an dieser einen
Stelle nur nicht erreicht.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.database.models import PatchedFixture
from src.core.show import show_file as SF


class _Sperre(Exception):
    """Steht fuer den gesperrten SQLite-Zugriff. Bewusst eine EIGENE Klasse:
    der Fix darf nicht an einem bestimmten Fehlertyp haengen — jeder Fehler beim
    Patch-Austausch muss gemeldet werden."""


class LadefehlerWirdGemeldetTest(unittest.TestCase):

    def setUp(self):
        from src.core.app_state import get_state
        self.st = get_state()
        SF.reset_show()

    def _patche(self, *labels):
        for i, name in enumerate(labels, start=1):
            self.st.add_fixture(PatchedFixture(
                fid=i, label=name, fixture_profile_id=1, mode_name="m",
                universe=1, address=i * 10, channel_count=8,
                fixture_type="par"), undoable=False)

    def _showdatei(self, *labels):
        pfad = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                            f"stab23_{os.getpid()}.lshow")
        SF.reset_show()
        self._patche(*labels)
        SF.save_show(pfad)
        SF.reset_show()
        return pfad

    def test_gescheiterter_patch_austausch_meldet_sich(self):
        pfad = self._showdatei("B-Wash 1", "B-Wash 2")
        self._patche("A-Spot 1", "A-Spot 2")

        echt = self.st.replace_patch
        self.st.replace_patch = lambda pfs: (_ for _ in ()).throw(_Sperre("database is locked"))
        try:
            ok, msg = SF.load_show(pfad)
        finally:
            self.st.replace_patch = echt

        self.assertTrue(SF.letzte_ladeprobleme(),
                        "Der Ladefehler taucht in letzte_ladeprobleme() nicht auf — "
                        "dann zeigt die UI auch keinen Warndialog")
        self.assertIn("konnten nicht gelesen werden", msg,
                      f"load_show meldet glatten Erfolg: {msg!r}")
        # Rueckgabewert bleibt bewusst True: die Show IST offen, nur unvollstaendig
        # (QA-50-Entscheidung; ein False liesse Aufrufer sie als Fehlschlag werfen).
        self.assertTrue(ok)

    def test_gescheiterte_gruppen_wiederherstellung_meldet_sich(self):
        pfad = self._showdatei("B-Wash 1")

        # Nicht die Funktion ersetzen, sondern IHRE Innerei scheitern lassen —
        # sonst prueft der Test seine eigene Nachbildung statt des Codepfads.
        orig_session = self.st._session
        self.st._session = lambda: (_ for _ in ()).throw(_Sperre("database is locked"))
        try:
            SF.load_show(pfad)
        finally:
            self.st._session = orig_session

        self.assertTrue(
            any("groups" in p for p in SF.letzte_ladeprobleme()),
            f"Gruppen-Fehler nicht gemeldet: {SF.letzte_ladeprobleme()}")

    # ── Positivkontrolle ─────────────────────────────────────────────────────

    def test_sauberes_laden_meldet_weiterhin_glatt(self):
        """Ohne Fehler darf nichts in der Problemliste stehen — sonst wuerde die
        UI bei JEDEM Laden warnen und die Warnung waere wertlos."""
        pfad = self._showdatei("B-Wash 1", "B-Wash 2")
        ok, msg = SF.load_show(pfad)

        self.assertTrue(ok)
        self.assertEqual(SF.letzte_ladeprobleme(), [])
        self.assertNotIn("ABER", msg)
        self.assertEqual(
            sorted(f.label for f in self.st.get_patched_fixtures()),
            ["B-Wash 1", "B-Wash 2"])


class MeldeketteIstVerdrahtetTest(unittest.TestCase):
    """Strukturell: die beiden Lade-Schluckpunkte MUESSEN ueber ``_lenient``
    laufen. Ein blosses ``print`` an dieser Stelle ist genau der Fehler."""

    def test_patch_austausch_nutzt_lenient(self):
        gemeldet = []
        echt = SF._lenient
        SF._lenient = lambda msg, exc: gemeldet.append(msg)
        try:
            class _State:
                _suppress_emits = False

                def replace_patch(self, pfs):
                    raise _Sperre("boom")

            SF._replace_patch_from_data(_State(), [])
        finally:
            SF._lenient = echt

        self.assertTrue(gemeldet,
                        "_replace_patch_from_data schluckt den Fehler weiterhin "
                        "still — der Aufrufer kann ihn dann nicht melden")


if __name__ == "__main__":
    unittest.main()
