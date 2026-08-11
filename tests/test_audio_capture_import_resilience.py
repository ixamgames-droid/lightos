"""Linux-Audio: ein beim Import nicht erreichbarer PulseAudio-Server ist soft.

★★ QA-52: Dieser Test las bis hierhin den QUELLTEXT und suchte darin zwei
Zeichenketten (``"except Exception as exc:"`` und ``"HAS_SOUNDCARD = False"``).
Damit bestand er auch dann, wenn der Block an der falschen Stelle steht, das
falsche umschliesst oder gar nicht mehr ausgefuehrt wird — und er waere rot
geworden, sobald jemand den Fehler in eine Variable umbenennt, ohne dass sich
am Verhalten irgendetwas aendert. **Er prueft jetzt den Vorgang selbst:** das
Modul wird mit einem ``soundcard`` importiert, das beim Import wirft.

Der Fall ist real: ``soundcard`` initialisiert PulseAudio schon beim Import und
wirft unter Linux u. a. ``AssertionError`` statt ``ImportError``, wenn der
Server nicht bereit ist. Ein ``except ImportError`` haette das nicht gefangen —
LightOS und die gesamte Testsuite waeren beim Modulimport gestorben.
"""
import builtins
import importlib
import sys
import unittest
from unittest import mock


def _lade_capture_mit_import_fehler(fehler: BaseException):
    """``src.core.audio.capture`` frisch importieren, wobei ``import soundcard``
    ``fehler`` wirft. Gibt das geladene Modul zurueck."""
    echt = builtins.__import__

    def gefaelscht(name, *a, **kw):
        if name == "soundcard":
            raise fehler
        return echt(name, *a, **kw)

    vorher = sys.modules.pop("src.core.audio.capture", None)
    sys.modules.pop("soundcard", None)
    try:
        with mock.patch.object(builtins, "__import__", gefaelscht):
            return importlib.import_module("src.core.audio.capture")
    finally:
        sys.modules.pop("src.core.audio.capture", None)
        if vorher is not None:
            sys.modules["src.core.audio.capture"] = vorher


class ImportBleibtWeichTest(unittest.TestCase):

    def test_assertionerror_beim_import_toetet_das_modul_nicht(self):
        """★ Der reale Linux-Fall: PulseAudio nicht bereit -> AssertionError.

        ``except ImportError`` haette hier nicht gegriffen — genau deshalb
        steht dort ``except Exception``.
        """
        modul = _lade_capture_mit_import_fehler(
            AssertionError("pulseaudio not ready"))
        self.assertFalse(modul.HAS_SOUNDCARD)
        self.assertIsNone(modul.sc)

    def test_auch_ein_gewoehnlicher_importerror_ist_weich(self):
        modul = _lade_capture_mit_import_fehler(
            ImportError("No module named 'soundcard'"))
        self.assertFalse(modul.HAS_SOUNDCARD)

    def test_der_rest_des_moduls_bleibt_benutzbar(self):
        """Weich abfangen heisst nicht „halb geladen": die Klasse muss stehen,
        sonst stirbt der Import eine Ebene weiter oben."""
        modul = _lade_capture_mit_import_fehler(RuntimeError("kaputt"))
        self.assertTrue(hasattr(modul, "AudioCapture"))
        self.assertEqual(44100, modul.SAMPLE_RATE)

    def test_positivkontrolle_mit_vorhandenem_soundcard(self):
        """★ Ohne sie belegte der Test nur, dass ein Fehler still bleibt — nicht,
        dass der Erfolgsfall ueberhaupt noch erreichbar ist. Ein ``HAS_SOUNDCARD
        = False`` als Konstante haette alle Tests oben bestanden."""
        echt = builtins.__import__
        attrappe = mock.MagicMock(name="soundcard")

        def gefaelscht(name, *a, **kw):
            if name == "soundcard":
                sys.modules["soundcard"] = attrappe
                return attrappe
            return echt(name, *a, **kw)

        vorher = sys.modules.pop("src.core.audio.capture", None)
        sys.modules.pop("soundcard", None)
        try:
            with mock.patch.object(builtins, "__import__", gefaelscht):
                modul = importlib.import_module("src.core.audio.capture")
            self.assertTrue(modul.HAS_SOUNDCARD)
            self.assertIs(attrappe, modul.sc)
        finally:
            sys.modules.pop("src.core.audio.capture", None)
            sys.modules.pop("soundcard", None)
            if vorher is not None:
                sys.modules["src.core.audio.capture"] = vorher


if __name__ == "__main__":
    unittest.main()
