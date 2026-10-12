"""PROC-21: ein Test laesst den globalen Zustand so zurueck, wie er ihn fand.

Zwei Verschmutzungen aus dem Einzelprozess-Lauf (Sitzung A, 12.10.2026) — beide
im Gate unsichtbar, weil dort jede Testdatei ihren eigenen Prozess hat:

1. **Patch.** ``test_allwhite_covers_all`` liess drei Moving Heads und eine Bar
   im globalen Zustand stehen. ``test_out61_estop_lade_fenster`` misst auf
   Universum 1, Adresse 40 — dort sass danach der Pan-Kanal eines Movers, und
   der Renderer schrieb seinen Grundwert hinein (127 statt 255).
2. **Bus-Abos.** Ein ``MainWindow`` aus ``setUpClass`` blieb am globalen
   Ereignis-Bus angemeldet (``test_las31_notaus_kopfleiste``). Die Sicherung
   in ``conftest`` galt nur je Test; ``setUpClass`` laeuft davor. Lud ein
   spaeterer Test eine Show, lief das alte Fenster mit und verbrauchte den
   einmaligen Sperrzonen-Hinweis (``test_las32_nachbesserung``).

Die Klassen dieser Datei laufen in der Reihenfolge, in der sie hier stehen:
erst der „Verschmutzer“, dann der Pruefer. Programmcode aendert PROC-21 nicht.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.sync import SyncEvent, get_sync                    # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _angemeldet(cb, ereignis=SyncEvent.SHOW_LOADED) -> bool:
    return cb in get_sync()._subscribers.get(ereignis, [])


# ══════════════════════════════════════════════════════════════════════════════
# 1) Abos aus setUpClass (unittest) ueberleben die Klasse nicht
# ══════════════════════════════════════════════════════════════════════════════

def _abo_aus_setupclass(*_a):
    """Steht fuer ``MainWindow._on_show_loaded``."""


class A1_MeldetInSetUpClassAn(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        get_sync().subscribe(SyncEvent.SHOW_LOADED, _abo_aus_setupclass)

    def test_waehrend_der_klasse_ist_es_da(self):
        self.assertTrue(_angemeldet(_abo_aus_setupclass))

    def test_auch_im_zweiten_test_noch(self):
        """Die Sicherung je Test darf das Abo der Klasse nicht wegnehmen."""
        self.assertTrue(_angemeldet(_abo_aus_setupclass))


class A2_DanachIstEsWeg(unittest.TestCase):

    def test_das_abo_der_vorigen_klasse_ist_abgemeldet(self):
        self.assertFalse(
            _angemeldet(_abo_aus_setupclass),
            "ein Abo aus setUpClass hat seine Klasse ueberlebt — ein spaeterer "
            "Test bekaeme Besuch von einem alten Fenster")


# ══════════════════════════════════════════════════════════════════════════════
# 2) dasselbe fuer setup_class (pytest-Stil)
# ══════════════════════════════════════════════════════════════════════════════

def _abo_aus_setup_class(*_a):
    pass


class TestB1MeldetInSetupClassAn:

    @classmethod
    def setup_class(cls):
        get_sync().subscribe(SyncEvent.PATCH_CHANGED, _abo_aus_setup_class)

    def test_waehrend_der_klasse_ist_es_da(self):
        assert _angemeldet(_abo_aus_setup_class, SyncEvent.PATCH_CHANGED)


class TestB2DanachIstEsWeg:

    def test_das_abo_der_vorigen_klasse_ist_abgemeldet(self):
        assert not _angemeldet(_abo_aus_setup_class, SyncEvent.PATCH_CHANGED)


# ══════════════════════════════════════════════════════════════════════════════
# 3) ein Abo, das VOR der Klasse da war, bleibt
# ══════════════════════════════════════════════════════════════════════════════

def _dauer_abo(*_a):
    pass


@pytest.fixture(scope="module")
def dauer_abo():
    get_sync().subscribe(SyncEvent.REFRESH_ALL, _dauer_abo)
    yield
    get_sync().unsubscribe(SyncEvent.REFRESH_ALL, _dauer_abo)


@pytest.mark.usefixtures("dauer_abo")
class TestC1EineKlasseDazwischen:

    def test_laeuft(self):
        assert _angemeldet(_dauer_abo, SyncEvent.REFRESH_ALL)


@pytest.mark.usefixtures("dauer_abo")
class TestC2DasAeltereAboIstNochDa:

    def test_die_sicherung_je_klasse_nimmt_nur_weg_was_die_klasse_brachte(self):
        assert _angemeldet(_dauer_abo, SyncEvent.REFRESH_ALL)


# ══════════════════════════════════════════════════════════════════════════════
# 4) die beiden gemeldeten Reihenfolgen, je in EINEM Prozess
# ══════════════════════════════════════════════════════════════════════════════

def _in_einem_prozess(*dateien) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         *[os.path.join("tests", d) for d in dateien]],
        cwd=_REPO, capture_output=True, text=True, timeout=240,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@pytest.mark.timeout(300)     # startet einen eigenen pytest-Lauf
def test_alles_weiss_vor_dem_notaus_im_lade_fenster():
    """Die gemeldete Reihenfolge: vorher 2 rot (127 statt 255)."""
    lauf = _in_einem_prozess("test_allwhite_covers_all.py",
                             "test_out61_estop_lade_fenster.py")
    assert lauf.returncode == 0, lauf.stdout[-2000:]


@pytest.mark.timeout(300)     # startet einen eigenen pytest-Lauf
def test_alles_weiss_laesst_keinen_patch_zurueck():
    """Der Verursacher selbst: nach seiner Datei ist der Patch leer — egal,
    wer danach misst."""
    code = (
        "import pytest, sys\n"
        "rc = pytest.main(['-q', '-p', 'no:cacheprovider', "
        "'tests/test_allwhite_covers_all.py'])\n"
        "from src.core.app_state import get_state\n"
        "rest = [(f.fid, f.universe, f.address) for f in get_state().get_patched_fixtures()]\n"
        "print('REST', rest)\n"
        "sys.exit(rc or (3 if rest else 0))\n")
    lauf = subprocess.run([sys.executable, "-c", code], cwd=_REPO,
                          capture_output=True, text=True, timeout=240,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert lauf.returncode == 0, lauf.stdout[-2000:]
    assert "REST []" in lauf.stdout
