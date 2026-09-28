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
import contextlib
import importlib
import sys
import unittest
from unittest import mock

_MOD = "src.core.audio.capture"
_FEHLT = object()


@contextlib.contextmanager
def _frischer_import():
    """Raum fuer einen FRISCHEN Import von ``src.core.audio.capture`` — und danach
    alles so zurueck, wie es war (QA-79).

    Ein Frischimport veraendert DREI Stellen, nicht eine: ``sys.modules[_MOD]``,
    ``sys.modules["soundcard"]`` und das Attribut ``capture`` am Paket
    ``src.core.audio`` (das setzt der Import-Mechanismus auf das NEUE Modul).
    Bis 2026-09-28 stellten beide Hilfen nur die erste wieder her. Folge: jedes
    spaetere ``from src.core.audio import capture`` bekam das Wegwerf-Modul, und
    Tests, die ``capture.HAS_SOUNDCARD`` oder ``get_audio_capture`` patchen, patchten
    am falschen Objekt — gemessen 4 bis 18 Fehlschlaege im selben Prozess, jede
    Datei einzeln gruen. Und das echte ``soundcard`` fehlte danach in
    ``sys.modules``, der naechste Import haette PulseAudio neu initialisiert."""
    import src.core.audio as paket
    vorher_mod = sys.modules.pop(_MOD, _FEHLT)
    vorher_sc = sys.modules.pop("soundcard", _FEHLT)
    vorher_attr = paket.__dict__.get("capture", _FEHLT)
    try:
        yield
    finally:
        for name, alt in ((_MOD, vorher_mod), ("soundcard", vorher_sc)):
            sys.modules.pop(name, None)
            if alt is not _FEHLT:
                sys.modules[name] = alt
        if vorher_attr is _FEHLT:
            paket.__dict__.pop("capture", None)
        else:
            paket.capture = vorher_attr


def _lade_capture_mit_import_fehler(fehler: BaseException):
    """``src.core.audio.capture`` frisch importieren, wobei ``import soundcard``
    ``fehler`` wirft. Gibt das geladene Modul zurueck."""
    echt = builtins.__import__

    def gefaelscht(name, *a, **kw):
        if name == "soundcard":
            raise fehler
        return echt(name, *a, **kw)

    with _frischer_import():
        with mock.patch.object(builtins, "__import__", gefaelscht):
            return importlib.import_module(_MOD)


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

        with _frischer_import():
            with mock.patch.object(builtins, "__import__", gefaelscht):
                modul = importlib.import_module(_MOD)
            self.assertTrue(modul.HAS_SOUNDCARD)
            self.assertIs(attrappe, modul.sc)


class HinterlaesstNichtsTest(unittest.TestCase):
    """★ QA-79: der eigentliche Vertrag dieser Datei — nach jedem Frischimport ist
    der Prozess wieder im Ausgangszustand. Genau das hat bisher niemand geprueft."""

    def _stand(self):
        import src.core.audio as paket
        return (sys.modules.get(_MOD), sys.modules.get("soundcard"),
                paket.__dict__.get("capture"))

    def test_fehlerfall_stellt_alle_drei_stellen_wieder_her(self):
        import src.core.audio.capture  # noqa: F401 — Ausgangszustand: echtes Modul geladen
        vorher = self._stand()
        _lade_capture_mit_import_fehler(AssertionError("pulseaudio not ready"))
        nachher = self._stand()
        for name, a, b in zip(("sys.modules[capture]", "sys.modules[soundcard]",
                               "src.core.audio.capture"), vorher, nachher):
            self.assertIs(a, b, name)

    def test_paketattribut_zeigt_danach_auf_dasselbe_modul_wie_sys_modules(self):
        """Die Form, in der der Fehler andere Dateien traf: ``from src.core.audio
        import capture`` und ``sys.modules`` liefern verschiedene Objekte."""
        import src.core.audio.capture  # noqa: F401
        _lade_capture_mit_import_fehler(ImportError("weg"))
        from src.core.audio import capture as ueber_paket
        self.assertIs(ueber_paket, sys.modules[_MOD])


if __name__ == "__main__":
    unittest.main()
