"""QA-60: Die Suite schrieb weiter in den echten Datenordner des Nutzers.

QA-54 hat die Schreib*funktionen* der Bibliothek bewacht, QA-58 ihren *Pfad*.
Beides half nur der Bibliothek. Alles Uebrige, was ``app_data_dir()`` benutzt —
``snapshots.json``, ``stages/``, ``ui_prefs.json``, ``input_profiles/``,
``shows/``, ``vc_assets/`` — landete weiterhin in ``~/.local/share/LightOS``:
``conftest.py`` lenkte nur ``APPDATA`` um, und das sieht ``app_data_dir()`` auf
Linux gar nicht.

★ **Dieselbe Lehre wie bei den Vorgaengern: was einzeln gepinnt wird, deckt nur
ab, woran jemand gedacht hat.** Deshalb prueft dieser Waechter nicht einzelne
Dateien, sondern die **Wurzel** — den Ordner, aus dem alle anderen Pfade folgen.

Geprueft wird am **Pfad**, nicht am Inhalt. Ein Inhaltsvergleich waere auf einem
Rechner, dessen Ordner zufaellig gerade so aussieht wie erwartet, blind — genau
der Fehler, an dem der erste QA-58-Waechter scheiterte.
"""
import os
import unittest

_ECHTER_ORDNER = os.path.join(os.path.expanduser("~"), ".local", "share",
                              "LightOS")


def _aufgeloest(p: str) -> str:
    return os.path.realpath(os.path.expanduser(p))


class DatenordnerZeigtInDenSandkastenTest(unittest.TestCase):
    """Der Ordner, den die App benutzt, darf nicht der des Nutzers sein."""

    def test_app_data_dir_zeigt_nicht_auf_den_echten_ordner(self):
        from src.core.paths import app_data_dir
        benutzt = _aufgeloest(app_data_dir())
        self.assertNotEqual(
            _aufgeloest(_ECHTER_ORDNER), benutzt,
            "app_data_dir() zeigt auf den echten Datenordner des Nutzers — "
            "dann schreiben Snapshots, Stages, Prefs, Input-Profile und "
            "VC-Assets dorthin. conftest.py muss XDG_DATA_HOME umlenken, nicht "
            "nur APPDATA (das sieht app_data_dir auf Linux nicht).")

    def test_der_benutzte_ordner_liegt_im_test_bereich(self):
        """Nicht bloss „irgendwo anders\", sondern im Testbereich — sonst waere
        die Zusage mit einem beliebigen fremden Pfad auch erfuellt."""
        from src.core.paths import app_data_dir
        benutzt = _aufgeloest(app_data_dir())
        import tempfile
        self.assertTrue(
            benutzt.startswith(_aufgeloest(tempfile.gettempdir())),
            f"der benutzte Datenordner liegt nicht im Temp-Bereich: {benutzt}")

    def test_die_messung_wuerde_den_echten_ordner_auch_erkennen(self):
        """POSITIVKONTROLLE der Vergleichsmethode.

        Ohne sie koennte `_aufgeloest` beide Seiten auf denselben Wert bringen
        (oder auf None), und der Test oben bestuende, ohne etwas zu
        unterscheiden."""
        self.assertEqual(_aufgeloest(_ECHTER_ORDNER),
                         _aufgeloest(_ECHTER_ORDNER))
        self.assertNotEqual(_aufgeloest(_ECHTER_ORDNER),
                            _aufgeloest(os.path.join(_ECHTER_ORDNER, "x")))

    def test_die_bibliothek_wird_trotzdem_aus_dem_ECHTEN_ordner_kopiert(self):
        """★ Die Reihenfolge in conftest.py, als Test statt als Kommentar.

        `_ECHTE_FIXTURE_DB` wird aufgeloest, SOLANGE die Datenordner-Variablen
        noch echt sind. Wer die XDG-Umlenkung nach oben schoebe, liesse den
        QA-58-Waechter gegen den Sandkasten statt gegen die echte Bibliothek
        vergleichen — er wuerde nie wieder anschlagen, und niemand saehe es.
        """
        # ★ Das BEREITS GELADENE conftest befragen, nicht neu importieren.
        # Ein `import tests.conftest` laedt das Modul ein ZWEITES Mal unter
        # anderem Namen — und zu diesem Zeitpunkt ist XDG_DATA_HOME laengst
        # umgelenkt, `_ECHTE_FIXTURE_DB` zeigte dann in den Sandkasten. Der
        # Test haette also den Fehler gemeldet, den er sucht, obwohl der
        # Produktionscode richtig ist (beim ersten Anlauf genau so passiert).
        import sys
        conftests = [m for name, m in sys.modules.items()
                     if m is not None and name.rsplit(".", 1)[-1] == "conftest"
                     and hasattr(m, "_ECHTE_FIXTURE_DB")]
        self.assertTrue(conftests, "kein geladenes conftest mit _ECHTE_FIXTURE_DB")
        echte = conftests[0]._ECHTE_FIXTURE_DB
        self.assertEqual(
            _aufgeloest(_ECHTER_ORDNER), _aufgeloest(os.path.dirname(echte)),
            "_ECHTE_FIXTURE_DB zeigt nicht mehr in den echten Datenordner — "
            "dann wurde die XDG-Umlenkung VOR ihrer Aufloesung gesetzt, und "
            "der QA-58-Waechter vergleicht Sandkasten gegen Sandkasten.")


if __name__ == "__main__":
    unittest.main()
