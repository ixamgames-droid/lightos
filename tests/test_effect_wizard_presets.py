"""B1 / T-4 + EA-02: neue Effekt-Assistent-Presets (Wipe/Comet/Random-Strobe/VU)
und Farb-Zwischenstufen-Interpolation.

★★ QA-56 (Rest aus QA-52, Befund 7): diese Datei ersetzte **alle vier**
Wizard-Seiten durch Attrappen (``_Page0``…``_Page3``) und haengte sie per
``wiz.page = lambda i: [...][i]`` in den echten Wizard. Damit lief zwar
``_generate()``, aber die vier Seiten — also alles, was der Anwender bedient —
waren aus dem Test verschwunden: Typ-Liste, Lampen-Haken, Farb-Vorauswahl aus
dem Preset und die Tempo-Defaults kamen aus dem Testkoerper, nicht aus dem
Produktivcode. Geprueft wurde die Verdrahtung der Attrappen.

Jetzt wird der echte Assistent gebaut und **bedient**: Typ in der echten Liste
anklicken, mit ``next()`` weiterblaettern (das ruft die echten
``initializePage``-Haken), Haken/Farben/Zwischenstufen an den echten Widgets
setzen und mit ``accept()`` abschliessen. Attrappe bleibt nur die *Umgebung*
(gepatchtes Rig + Function-Manager) — nicht der Prueflung.
"""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

_app = QApplication.instance() or QApplication([])


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht.
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# ── Umgebung (kein Ersatz fuer Prueflung): ein gepatchtes Mini-Rig ────────────

class _Ch:
    def __init__(self, attr, channel_number):
        self.attribute = attr
        self.channel_number = channel_number
        self.ranges = []


class _Fx:
    def __init__(self, fid):
        self.fid = fid
        self.universe = 1
        self.address = 1
        self.label = f"FX {fid}"


# PAR mit RGB+W+Dimmer.
_PAR_CHANS = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
              _Ch("color_w", 4), _Ch("intensity", 5)]
_FIDS = [1, 2, 3]
_CH_R, _CH_G, _CH_B, _CH_W, _CH_INT = 1, 2, 3, 4, 5


@contextmanager
def _gepatchtes_rig(fids=_FIDS, vorauswahl=()):
    """Patcht NUR die Umgebung: gepatchte Geraete, deren Kanaele und einen
    frischen Function-Manager. Der Assistent selbst bleibt echt."""
    import src.core.app_state as app_state
    import src.core.engine.function_manager as fm_mod
    from src.core.engine.function_manager import FunctionManager

    fm = FunctionManager()
    fixtures = [_Fx(f) for f in fids]
    fake_state = type("S", (), {
        "get_patched_fixtures": lambda self: list(fixtures),
        "get_selected_fids": lambda self: list(vorauswahl),
    })()
    orig = (app_state.get_state, app_state.get_channels_for_patched, fm_mod._manager)
    app_state.get_state = lambda: fake_state
    app_state.get_channels_for_patched = lambda fx: _PAR_CHANS
    fm_mod._manager = fm
    try:
        yield fm
    finally:
        (app_state.get_state, app_state.get_channels_for_patched,
         fm_mod._manager) = orig


def _typ_anklicken(wiz, key):
    """Seite 1 wie der Anwender bedienen: die Zeile mit dem Preset-LABEL waehlen.
    Der Test kennt nur, was auf dem Schirm steht — dass daran der richtige
    Schluessel haengt, ist Sache von ``_TypePage``."""
    from src.ui.widgets.effect_wizard import PRESETS
    label = dict((p[0], p[1]) for p in PRESETS)[key]
    lst = wiz.page(0).list
    for row in range(lst.count()):
        if lst.item(row).text().startswith(label):
            lst.setCurrentRow(row)
            return
    raise AssertionError(f"Preset '{label}' steht nicht in der Typ-Liste")


def _knopf(page, text):
    for b in page.findChildren(QPushButton):
        if b.text() == text:
            return b
    raise AssertionError(f"Knopf '{text}' fehlt auf der Seite")


def _assistent_fuehren(key, *, lampen=None, farben=None, zwischenstufen=None,
                       name=None, fids=_FIDS, vorauswahl=()):
    """Baut den ECHTEN Assistenten und blaettert ihn durch alle vier Seiten.

    Rueckgabe: (fm, wiz, warnungen). ``warnungen`` sammelt die
    ``QMessageBox.warning``-Aufrufe aus ``accept()`` — ein Fehlschlag der
    Erzeugung meldet sich dort und wuerde sonst als „nichts passiert"
    durchrutschen (und die modale Box haette den Test aufgehaengt).
    """
    from src.ui.widgets.effect_wizard import EffectWizard

    with _gepatchtes_rig(fids=fids, vorauswahl=vorauswahl) as fm:
        wiz = EffectWizard()
        wiz.restart()                      # Seite 1 aktiv (echter Wizard-Start)
        _typ_anklicken(wiz, key)
        wiz.next()                         # -> Seite 2 (Lampen)
        if lampen is not None:
            _knopf(wiz.page(1), "Keine").click()
            for cb in wiz.page(1).checks:
                if cb.fid in lampen:
                    cb.setChecked(True)
        wiz.next()                         # -> Seite 3 (Farben, initializePage)
        if farben is not None:
            for b in wiz.page(2).swatch_btns:
                if b.isChecked() != (b.rgb in farben):
                    b.click()
        if zwischenstufen is not None:
            wiz.page(2)._interp_chk.setChecked(True)
            wiz.page(2)._interp_spin.setValue(zwischenstufen)
        wiz.next()                         # -> Seite 4 (Tempo/Name, initializePage)
        if name is not None:
            wiz.page(3).name.setText(name)
        warnungen = []
        with patch.object(QMessageBox, "warning",
                          staticmethod(lambda *a, **k: warnungen.append(a))):
            wiz.accept()                   # echter Abschluss-Pfad inkl. _generate
        return fm, wiz, warnungen


def _erzeugten_chaser(key, **kw):
    fm, wiz, warnungen = _assistent_fuehren(key, **kw)
    assert warnungen == [], f"Assistent meldete einen Fehler: {warnungen}"
    assert wiz.created_function is not None, "kein Chaser erzeugt"
    return fm, wiz.created_function


def _werte(scene):
    """{(fid, kanal): wert} einer erzeugten Szene."""
    return {(sv.fixture_id, sv.channel): sv.value for sv in scene.values}


class NewPresetsTest(unittest.TestCase):
    def test_presets_registered(self):
        from src.ui.widgets.effect_wizard import PRESETS
        keys = {p[0] for p in PRESETS}
        for k in ("wipe", "comet", "random_strobe", "vu"):
            self.assertIn(k, keys)

    def test_wipe_cumulative_fill(self):
        fm, ch = _erzeugten_chaser("wipe")
        self.assertEqual(len(ch.steps), len(_FIDS))   # eine Stufe je Lampe
        first = fm.get(ch.steps[0].function_id)
        last = fm.get(ch.steps[-1].function_id)
        first_fids = {sv.fixture_id for sv in first.values}
        last_fids = {sv.fixture_id for sv in last.values}
        self.assertEqual(first_fids, {1})             # erste Stufe nur Lampe 1
        self.assertEqual(last_fids, set(_FIDS))        # letzte Stufe alle
        # Die Farbe kommt aus der Preset-Vorauswahl der ECHTEN Farbseite
        # (Wipe = blau). Mit Attrappe stand sie im Test.
        w = _werte(last)
        self.assertEqual((w[(3, _CH_R)], w[(3, _CH_G)], w[(3, _CH_B)]), (0, 0, 255))

    def test_comet_head_full_tail_dimmer(self):
        fm, ch = _erzeugten_chaser("comet")
        self.assertEqual(len(ch.steps), len(_FIDS))
        # Im 3. Schritt (Kopf an Lampe 3) ist Lampe 3 voll, Lampe 2 gedimmt.
        s = fm.get(ch.steps[2].function_id)
        inten = {sv.fixture_id: sv.value for sv in s.values if sv.channel == _CH_INT}
        self.assertEqual(inten.get(3), 255)
        self.assertTrue(0 < inten.get(2, 0) < 255)

    def test_random_strobe_random_order(self):
        from src.core.engine.function import RunOrder
        fm, ch = _erzeugten_chaser("random_strobe")
        self.assertEqual(len(ch.steps), len(_FIDS))
        self.assertEqual(ch.run_order, RunOrder.Random)

    def test_vu_bounces_up_and_down(self):
        fm, ch = _erzeugten_chaser("vu")
        # levels = 1,2,3,2,1 -> 2n-1 Schritte
        self.assertEqual(len(ch.steps), 2 * len(_FIDS) - 1)


class EchteSeitenTest(unittest.TestCase):
    """QA-56: was die vier Attrappen-Seiten strukturell nicht pruefen konnten."""

    def test_abgewaehlte_lampe_faellt_aus_dem_effekt(self):
        """Seite 2 echt bedient: „Keine" druecken, zwei Haken setzen."""
        fm, ch = _erzeugten_chaser("wipe", lampen={1, 3})
        self.assertEqual(len(ch.steps), 2, "nur die angehakten Lampen ergeben Stufen")
        alle_fids = set()
        for st in ch.steps:
            alle_fids |= {sv.fixture_id for sv in fm.get(st.function_id).values}
        self.assertEqual(alle_fids, {1, 3}, "Lampe 2 war abgewaehlt")

    def test_vorauswahl_aus_dem_programmer_kreuzt_nur_diese_an(self):
        """R2: liegt eine Programmer-Auswahl vor, startet Seite 2 mit genau
        diesen Haken — ohne dass der Test einen Haken anfasst."""
        fm, ch = _erzeugten_chaser("wipe", vorauswahl=(2,))
        self.assertEqual(len(ch.steps), 1)
        self.assertEqual({sv.fixture_id for sv in fm.get(ch.steps[0].function_id).values},
                         {2})

    def test_tempo_und_name_kommen_von_der_echten_optionsseite(self):
        """Seite 4 echt: ``initializePage`` setzt Name und Tempo-Defaults des
        Presets (Wipe: 0.15 s Halten / 0.10 s Fade, taktgleich)."""
        fm, ch = _erzeugten_chaser("wipe")
        self.assertEqual(ch.name, "Wipe")
        self.assertAlmostEqual(ch.steps[0].hold, 0.15, places=6)
        self.assertAlmostEqual(ch.steps[0].fade_in, 0.10, places=6)
        self.assertEqual(ch.tempo_bus_id, "Global", "Wipe laeuft laut Preset im Beat")

    def test_preset_ohne_beat_haengt_nicht_am_tempo_bus(self):
        """Positivkontrolle zur Beat-Zusicherung: Strobe steht im Preset auf
        „nicht taktgleich" — der Haken darf also NICHT gesetzt sein."""
        fm, ch = _erzeugten_chaser("strobe")
        self.assertEqual(ch.tempo_bus_id, "")

    def test_zwischenstufen_der_echten_farbseite_verlaengern_den_chaser(self):
        """EA-02 durch den ganzen Assistenten: Haken „Zwischenstufen" auf der
        echten Seite 3 -> 3 Preset-Farben x (1+4) = 15 Stufen."""
        fm, ch = _erzeugten_chaser("color_chase", zwischenstufen=4)
        self.assertEqual(len(ch.steps), 15)
        fm2, ch2 = _erzeugten_chaser("color_chase")
        self.assertEqual(len(ch2.steps), 3, "ohne Haken bleiben es die 3 Farben")

    def test_gewaehlte_farbe_landet_auf_den_kanaelen(self):
        """Seite 3 echt bedient: Preset-Vorauswahl abwaehlen, Gruen anklicken."""
        fm, ch = _erzeugten_chaser("wipe", farben=[(0, 255, 0)])
        w = _werte(fm.get(ch.steps[0].function_id))
        self.assertEqual((w[(1, _CH_R)], w[(1, _CH_G)], w[(1, _CH_B)]), (0, 255, 0))

    def test_ohne_lampe_meldet_der_assistent_den_fehler(self):
        """Negativ-/Positivkontrolle in einem: „Keine" druecken und abschliessen
        -> Warnung statt stiller Leer-Chaser, und der Dialog bleibt offen."""
        fm, wiz, warnungen = _assistent_fuehren("wipe", lampen=set())
        self.assertEqual(len(warnungen), 1, "leere Auswahl muss gemeldet werden")
        self.assertIsNone(wiz.created_function)
        self.assertEqual(wiz.result(), 0, "accept() darf den Dialog nicht schliessen")


class ColorInterpolationTest(unittest.TestCase):
    def _page(self):
        from src.ui.widgets.effect_wizard import _ColorPage
        return _ColorPage()

    def test_off_returns_selected(self):
        page = self._page()
        for b in page.swatch_btns[:2]:
            b.setChecked(True)
        self.assertEqual(page.expanded_colors(), page.selected_colors())

    def test_interpolation_expands_with_wrap(self):
        page = self._page()
        # genau 2 Farben anwählen
        for b in page.swatch_btns:
            b.setChecked(False)
        page.swatch_btns[0].setChecked(True)   # Rot
        page.swatch_btns[3].setChecked(True)   # Grün
        page._interp_chk.setChecked(True)
        page._interp_spin.setValue(4)
        exp = page.expanded_colors()
        # 2 Farben * (1 + 4 Zwischen) = 10 (mit Wrap last->first)
        self.assertEqual(len(exp), 10)
        self.assertEqual(exp[0], page.swatch_btns[0].rgb)   # beginnt mit Rot


if __name__ == "__main__":
    unittest.main()
