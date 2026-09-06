"""UI-59 + UI-60 — der Layer-Editor sperrt nur, was wirklich sinnlos ist, und
zeigt nur Felder, die etwas tun.

**UI-59 (absteigende Rampe war nicht eintippbar).** ``_set_layer_prop`` zog bei
``min > max`` die Gegen-Grenze NACH — kein Validator, daher „je nach
Eingabereihenfolge" mal Dauer-Schwarz, mal Dauer-Voll. Die eigentliche Ursache
liegt tiefer: ``min_val``/``max_val`` bedeuten je nach Layer-Typ etwas ANDERES,
und eine Regel galt fuer alle drei. An ``EffectLayer.process`` gemessen:

===== ======================= ============================ ==================
Typ    Bedeutung von min/max   min=1.0 / max=0.0 liefert    Urteil
===== ======================= ============================ ==================
RAMP   Endpunkte               [1.0, 0.8, 0.6, 0.4, 0.2]    sinnvoll
MAP    Eingangsbereich         [1.0, 0.5, 0.0]              sinnvoll
CLAMP  Grenzen                 konstant 0.8                 sinnlos, Sperre ok
===== ======================= ============================ ==================

Deshalb haengt die Sperre am TYP. Pauschal freigeben macht CLAMP kaputt,
pauschal sperren nimmt zwei sinnvolle Einstellungen weg — die Tests hier halten
BEIDE Richtungen fest.

Der wichtigste Test ist ``test_gemessen_wo_vertauschte_grenzen_die_wirkung_toeten``:
er misst am echten ``process``, ob vertauschte Grenzen den Layer entarten
lassen, statt meine Behauptung darueber zu wiederholen.

**UI-60 (acht wirkungslose Felder beim frischen Effekt).** Die Regel „nur zeigen,
was der Layer auswertet" existierte bereits und ist richtig — sie lief nur ueber
``_on_select``, und der feuert ohne Auswahl nie. Gemessen vor dem Fix: frischer
Effekt = 0 Layer, 8 sichtbare Felder. Ausgeblendet, NICHT deaktiviert: eine
deaktivierte Zeile sieht im App-Stylesheet aus wie eine bedienbare — auch das
haelt hier ein Test fest.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.effect_layers import (EffectLayer, LayerType,   # noqa: E402
                                           used_fields)
from src.ui.views.effect_layer_editor import (                       # noqa: E402
    grenzen_muessen_geordnet_sein)

# Nicht entartete Basis: MAPs Ausgangsbereich (offset..value) muss eine Breite
# haben, sonst kann min/max dort gar nichts bewirken und die Messung meldete
# „entartet" fuer einen Fehler in der MESSUNG.
_BASIS = dict(amplitude=0.8, frequency=1.0, phase=0.0, offset=0.0,
              value=1.0, min_val=0.2, max_val=0.8, fixture_phase_step=0.0)

# Eingaenge ueber die Grenzen HINAUS (-0.4 / 1.4) und ueber eine ganze
# Ramp-Periode: laegen alle Proben zwischen min und max, koennte ein Clamp gar
# nichts tun und die Messung meldete faelschlich „reagiert nicht".
_PROBEN = [(prev, t, 0)
           for prev in (-0.4, 0.15, 0.62, 1.4)
           for t in (0.0, 0.2, 0.45, 0.7, 0.9)]

_ALLE_FELDER = ("amplitude", "frequency", "phase", "offset", "value",
                "min_val", "max_val", "fixture_phase_step")


def _reagiert(layer) -> bool:
    """Aendert der ECHTE ``process`` seine Ausgabe ueber die Proben ueberhaupt?"""
    werte = {round(layer.process(prev, t, idx), 9) for prev, t, idx in _PROBEN}
    return len(werte) > 1


def _vertauscht(layer_type) -> EffectLayer:
    return EffectLayer(type=layer_type,
                       **{**_BASIS,
                          "min_val": _BASIS["max_val"],
                          "max_val": _BASIS["min_val"]})


class Ui59RegelTest(unittest.TestCase):
    """Die Typ-Regel, ohne gebautes Widget befragt."""

    def test_regel_beantwortet_jeden_layer_typ(self):
        """Ein neuer Typ darf nicht still in eine der beiden Antworten fallen,
        ohne dass jemand hinsieht."""
        for lt in LayerType:
            with self.subTest(lt=lt):
                self.assertIsInstance(grenzen_muessen_geordnet_sein(lt), bool)

    def test_clamp_bleibt_gesperrt_ramp_und_map_nicht(self):
        """Beide Richtungen an einer Stelle: pauschal freigeben UND pauschal
        sperren muessen hier scheitern."""
        self.assertTrue(grenzen_muessen_geordnet_sein(LayerType.CLAMP))
        self.assertFalse(grenzen_muessen_geordnet_sein(LayerType.RAMP))
        self.assertFalse(grenzen_muessen_geordnet_sein(LayerType.MAP))

    def test_typen_ohne_grenzfelder_werden_nicht_gesperrt(self):
        """Wo der Editor min/max gar nicht anbietet, gibt es nichts zu ordnen."""
        for lt in LayerType:
            if {"min_val", "max_val"} & used_fields(lt):
                continue
            with self.subTest(lt=lt):
                self.assertFalse(grenzen_muessen_geordnet_sein(lt))

    # ── der eigentliche Beweis ───────────────────────────────────────────────

    def test_gemessen_wo_vertauschte_grenzen_die_wirkung_toeten(self):
        """Am echten ``process`` gemessen statt behauptet: genau dort, wo
        ``min > max`` den Layer auf einen konstanten Wert einfriert, ist die
        Sperre richtig — und nur dort."""
        gemessen = []
        for lt in LayerType:
            if not {"min_val", "max_val"} <= used_fields(lt):
                continue
            gemessen.append(lt)
            with self.subTest(lt=lt):
                geordnet = EffectLayer(type=lt, **_BASIS)
                self.assertTrue(
                    _reagiert(geordnet),
                    f"Vorbedingung verletzt: {lt.value} reagiert schon mit "
                    f"GEORDNETEN Grenzen auf nichts — dann misst der Test die "
                    f"Basis, nicht die Vertauschung")
                entartet = not _reagiert(_vertauscht(lt))
                self.assertEqual(
                    entartet, grenzen_muessen_geordnet_sein(lt),
                    f"{lt.value}: gemessen entartet={entartet}, "
                    f"Regel sagt {grenzen_muessen_geordnet_sein(lt)}")
        self.assertEqual(
            set(gemessen),
            {LayerType.RAMP, LayerType.CLAMP, LayerType.MAP},
            "die Messung muss ihren Gegenstand erreichen — genau diese drei "
            "Typen werten min/max aus")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _EditorMixin:
    """Kein show()/repaint(): ein elternloses Widget anzuzeigen hat den
    Renderer headless schon einmal mitgerissen. Sichtbarkeit wird ueber
    ``isHidden`` gemessen, das dafuer kein Fenster braucht."""

    def _editor(self, *layer):
        from src.core.engine.effect_func import LayeredEffect
        from src.ui.views.effect_layer_editor import EffectLayerEditor
        _app()
        eff = LayeredEffect("Test")
        eff.layers.extend(layer)
        ed = EffectLayerEditor(eff)
        self.addCleanup(ed.deleteLater)
        return eff, ed

    def _gewaehlt(self, ed, idx):
        ed._list.setCurrentRow(idx)
        self.assertIsNotNone(ed._current_layer(),
                             "Vorbedingung: es ist ein Layer ausgewaehlt")
        return ed._current_layer()

    def _sichtbar(self, ed):
        """★ Feld UND Beschriftung — beide gehoeren zur Zeile.

        Die erste Fassung mass nur ``spin.isHidden()``. Damit ueberlebte eine
        Mutation, die den Alt-Qt-Zweig erzwingt (``setRowVisible`` faellt aus,
        der Fallback ``spin.setVisible(...)`` laeuft): das Eingabefeld
        verschwindet, die acht Beschriftungen bleiben stehen — „Amplitude:",
        „Frequenz (Hz):", „Min:", „Max:" … ohne irgendetwas daneben. Genau die
        Halbheit, die UI-60 abschaffen sollte.
        """
        offen = set()
        for attr, spin in ed._prop_rows.items():
            label = ed._props_form.labelForField(spin)
            if not spin.isHidden() or (label is not None and not label.isHidden()):
                offen.add(attr)
        return offen


class Ui59EditorTest(_EditorMixin, unittest.TestCase):
    """Kommt die Regel am Formular an — in beide Richtungen?"""

    def _tippen(self, ed, minimum, maximum, zuerst_max=False):
        if zuerst_max:
            ed._spin_max.setValue(maximum)
            ed._spin_min.setValue(minimum)
        else:
            ed._spin_min.setValue(minimum)
            ed._spin_max.setValue(maximum)

    def test_absteigende_rampe_laesst_sich_eintippen(self):
        for zuerst_max in (False, True):
            with self.subTest(zuerst_max=zuerst_max):
                eff, ed = self._editor(EffectLayer(type=LayerType.RAMP))
                layer = self._gewaehlt(ed, 0)
                self._tippen(ed, 1.0, 0.0, zuerst_max)
                self.assertEqual((layer.min_val, layer.max_val), (1.0, 0.0))
                # Die echte Rechnung aufrufen, nicht nachbauen.
                self.assertEqual(
                    [round(layer.process(0.0, t=t), 3)
                     for t in (0.0, 0.2, 0.4, 0.6, 0.8)],
                    [1.0, 0.8, 0.6, 0.4, 0.2])

    def test_rampe_zieht_die_gegen_grenze_nicht_nach(self):
        """Auch das ANZEIGEFELD darf nicht springen — sonst steht im Formular
        etwas anderes als im Layer."""
        eff, ed = self._editor(EffectLayer(type=LayerType.RAMP))
        self._gewaehlt(ed, 0)
        self._tippen(ed, 1.0, 0.0)
        self.assertEqual((ed._spin_min.value(), ed._spin_max.value()),
                         (1.0, 0.0))

    def test_invertierte_abbildung_laesst_sich_eintippen(self):
        for zuerst_max in (False, True):
            with self.subTest(zuerst_max=zuerst_max):
                eff, ed = self._editor(
                    EffectLayer(type=LayerType.MAP, offset=0.0, value=1.0))
                layer = self._gewaehlt(ed, 0)
                self._tippen(ed, 1.0, 0.0, zuerst_max)
                self.assertEqual((layer.min_val, layer.max_val), (1.0, 0.0))
                self.assertEqual(
                    [round(layer.process(p, t=0.0), 3)
                     for p in (0.0, 0.5, 1.0)],
                    [1.0, 0.5, 0.0])

    # ── Gegenprobe: die Sperre, wo sie hingehoert ────────────────────────────

    def test_clamp_zieht_weiterhin_nach(self):
        """Der Fix darf die Sperre nicht pauschal abschalten: ein Clamp mit
        min > max waere konstant und damit keine Grenze mehr."""
        for zuerst_max in (False, True):
            with self.subTest(zuerst_max=zuerst_max):
                eff, ed = self._editor(EffectLayer(type=LayerType.CLAMP))
                layer = self._gewaehlt(ed, 0)
                self._tippen(ed, 0.8, 0.2, zuerst_max)
                self.assertEqual(layer.min_val, layer.max_val)
                # und das Formular zeigt dieselbe Zahl wie der Layer
                self.assertEqual(ed._spin_min.value(), layer.min_val)
                self.assertEqual(ed._spin_max.value(), layer.max_val)

    def test_clamp_geordnete_eingabe_bleibt_unangetastet(self):
        """Die Sperre darf nur beim Ueberschreiten greifen."""
        eff, ed = self._editor(EffectLayer(type=LayerType.CLAMP))
        layer = self._gewaehlt(ed, 0)
        self._tippen(ed, 0.3, 0.7)
        self.assertEqual((layer.min_val, layer.max_val), (0.3, 0.7))

    def test_andere_felder_ruehren_die_grenzen_nicht_an(self):
        """Der fruehe Ausstieg darf das Setzen der uebrigen Felder nicht
        verschlucken."""
        eff, ed = self._editor(EffectLayer(type=LayerType.RAMP))
        layer = self._gewaehlt(ed, 0)
        ed._spin_freq.setValue(2.5)
        self.assertEqual(layer.frequency, 2.5)
        self.assertEqual((layer.min_val, layer.max_val), (0.0, 1.0))

    def test_ohne_auswahl_wird_nichts_geschrieben(self):
        eff, ed = self._editor(EffectLayer(type=LayerType.RAMP))
        self.assertEqual(ed._list.currentRow(), -1,
                         "Vorbedingung: nichts ausgewaehlt")
        ed._spin_min.setValue(1.0)
        ed._spin_max.setValue(0.0)
        self.assertEqual((eff.layers[0].min_val, eff.layers[0].max_val),
                         (0.0, 1.0))
        # Zusaetzlich DIREKT aufgerufen: eine Ausnahme im Slot verschwindet in
        # Qts Signal-Emission spurlos (gemessen — die Mutationsprobe „Wache
        # entfernt" blieb ueber den Spinbox-Weg gruen, ohne eine Zeile stderr).
        ed._set_layer_prop("min_val", 1.0)
        ed._set_layer_prop("max_val", 0.0)
        self.assertEqual((eff.layers[0].min_val, eff.layers[0].max_val),
                         (0.0, 1.0))


class Ui60SichtbarkeitTest(_EditorMixin, unittest.TestCase):
    """Ein Feld, das nichts tut, behauptet Wirkung."""

    def test_frischer_effekt_zeigt_kein_eigenschaftsfeld(self):
        eff, ed = self._editor()
        self.assertEqual(len(eff.layers), 0, "Vorbedingung: frischer Effekt")
        self.assertEqual(set(ed._prop_rows), set(_ALLE_FELDER),
                         "Vorbedingung: die acht Zeilen existieren ueberhaupt")
        self.assertEqual(self._sichtbar(ed), set())

    def test_geladener_effekt_ohne_auswahl_zeigt_kein_feld(self):
        """Dieselbe Luecke in zweiter Auspraegung: ein Effekt MIT Layern startet
        ohne Auswahl — auch dann darf kein Feld dastehen."""
        eff, ed = self._editor(EffectLayer(type=LayerType.CLAMP))
        self.assertEqual(ed._list.currentRow(), -1,
                         "Vorbedingung: nichts ausgewaehlt")
        self.assertEqual(self._sichtbar(ed), set())

    def test_nach_dem_loeschen_des_letzten_layers_wieder_leer(self):
        eff, ed = self._editor(EffectLayer(type=LayerType.CLAMP))
        self._gewaehlt(ed, 0)
        self.assertEqual(self._sichtbar(ed), {"min_val", "max_val"})
        ed._delete()
        self.assertEqual(len(eff.layers), 0)
        self.assertEqual(self._sichtbar(ed), set())

    # ── Gegenprobe: nicht einfach alles ausblenden ───────────────────────────

    def test_gewaehlter_clamp_zeigt_genau_min_und_max(self):
        eff, ed = self._editor(EffectLayer(type=LayerType.CLAMP))
        self._gewaehlt(ed, 0)
        self.assertEqual(self._sichtbar(ed), {"min_val", "max_val"})

    def test_gewaehlter_sinus_zeigt_die_wellen_felder(self):
        eff, ed = self._editor(EffectLayer(type=LayerType.SIN))
        self._gewaehlt(ed, 0)
        self.assertEqual(self._sichtbar(ed), used_fields(LayerType.SIN))

    def test_hinzugefuegter_layer_bringt_seine_felder_mit(self):
        """Der Weg des Nutzers: frischer Effekt, dann „+ Layer hinzufuegen"."""
        eff, ed = self._editor()
        ed._add_combo.setCurrentText(LayerType.CLAMP.value)
        ed._add_layer()
        self.assertEqual(len(eff.layers), 1)
        self.assertEqual(self._sichtbar(ed), {"min_val", "max_val"})

    def test_felder_sind_ausgeblendet_nicht_deaktiviert(self):
        """Verworfene Alternative festgenagelt: eine deaktivierte Zeile sieht im
        App-Stylesheet aus wie eine bedienbare."""
        eff, ed = self._editor()
        for attr, spin in ed._prop_rows.items():
            with self.subTest(attr=attr):
                self.assertTrue(spin.isHidden())
                self.assertTrue(spin.isEnabled())

    def test_grundeinstellungen_bleiben_stehen(self):
        """Der Fix darf nur die Layer-Eigenschaften betreffen — Name, Target,
        Base Value und Fixture-IDs gehoeren zum Effekt, nicht zum Layer."""
        eff, ed = self._editor()
        for widget in (ed._name_edit, ed._target_combo, ed._base_spin,
                       ed._fixtures_edit, ed._list):
            self.assertFalse(widget.isHidden())


if __name__ == "__main__":
    unittest.main()


# ─────────────────────────────────────────────────────────────────────────────
# Vom Skeptiker gefunden — beides gemessen, nicht erschlossen.
# ─────────────────────────────────────────────────────────────────────────────

class GetippteWerteUeberlebenTest(_EditorMixin, unittest.TestCase):
    """★★★ Der schwerere der beiden Befunde: die Nachzieh-Wache, die fuer CLAMP
    bewusst STEHEN BLEIBT, zerstoerte beim TIPPEN die bereits gesetzte
    Gegen-Grenze — unwiederbringlich.

    ``QDoubleSpinBox`` hat ``keyboardTracking=True``, also feuert
    ``valueChanged`` bei JEDEM Zeichen. Die erste „0" des Maximums zieht das
    Minimum auf 0.0; danach ist der Rest groesser und die Wache greift nie
    wieder.

    Gemessen vor dem Fix, echte Tastenanschlaege im Projekt-Locale::

        CLAMP  min "0,3" dann max "0,7"  ->  (0.0, 0.7)   getippt war (0.3, 0.7)
        CLAMP  min "0,8" dann max "0,2"  ->  (0.0, 0.2)   beworben ist (0.2, 0.2)

    ⚠️ Der zweite Fall ist der, FUER DEN die Wache da ist — sie lieferte nicht
    einmal dort ihr eigenes Versprechen, sondern eine dritte Zahl. Und „erst
    Min, dann Max" ist die natuerlichste aller Eingaben, kein Verdreher.

    ★ Alle bisherigen Tests trieben die Spinbox ueber ``setValue`` — ein Sprung
    auf den fertigen Wert. Der Zwischenzustand beim Tippen war damit voellig
    unbeobachtet, und genau dort sass der Schaden. Ein Test, der anders bedient
    als ein Mensch, misst etwas anderes.
    """

    def _tastatur(self, spin, zahl: float):
        """Eine Zahl so eintippen, wie ein Mensch es tut — Zeichen fuer Zeichen.

        ★★ Der Dezimaltrenner kommt aus dem WIDGET, nicht aus dieser Datei.
        Erste Fassung tippte ein festes Komma, weil dieser Rechner de_DE
        benutzt. In der CI laeuft die C-Locale mit Punkt: dort verschluckt die
        Spinbox das Komma, aus "0,3" wird 3.0, und alle vier Tests fielen —
        **auf gruener Maschine unbemerkt**. Eine Sonde muss dieselbe Konvention
        benutzen wie das, was sie bedient; die eigene Umgebung ist keine.
        """
        from PySide6.QtTest import QTest
        trenner = spin.locale().decimalPoint()
        text = ("%.4f" % zahl).rstrip("0").rstrip(".") or "0"
        text = text.replace(".", trenner)
        spin.lineEdit().selectAll()
        QTest.keyClicks(spin.lineEdit(), text)
        spin.interpretText()
        # Hausregel 2: erst belegen, dass die Tastenanschlaege ueberhaupt die
        # gemeinte Zahl ergeben haben. Sonst vergleicht der Test danach zwei
        # Zahlen, von denen keine die getippte ist — genau das ist passiert.
        self.assertAlmostEqual(
            spin.value(), zahl, places=6,
            msg=f"die Eingabe {text!r} ergab {spin.value()} statt {zahl} — "
                f"Dezimaltrenner des Widgets ist {trenner!r}")

    def _getippt(self, typ, erst: float, dann: float):
        eff, ed = self._editor(EffectLayer(type=typ, min_val=0.0, max_val=1.0))
        self._gewaehlt(ed, 0)
        self._tastatur(ed._spin_min, erst)
        self._tastatur(ed._spin_max, dann)
        l = eff.layers[0]
        return round(l.min_val, 3), round(l.max_val, 3)

    def test_clamp_behaelt_die_getippte_untergrenze(self):
        """★★★ Der Kern: erst Min, dann Max — die alltaegliche Reihenfolge."""
        self.assertEqual(self._getippt(LayerType.CLAMP, 0.3, 0.7), (0.3, 0.7))

    def test_clamp_liefert_bei_verdrehter_eingabe_was_es_verspricht(self):
        """★★ Der Fall, fuer den die Wache ueberhaupt existiert. Vorher kam
        weder die Eingabe noch die Korrektur heraus, sondern (0.0, 0.2)."""
        self.assertEqual(self._getippt(LayerType.CLAMP, 0.8, 0.2), (0.2, 0.2))

    def test_die_absteigende_rampe_ist_auch_ueber_die_tastatur_erreichbar(self):
        """Der eigentliche Zweck von UI-59, am echten Bedienweg."""
        self.assertEqual(self._getippt(LayerType.RAMP, 1.0, 0.0), (1.0, 0.0))

    def test_eine_gewoehnliche_rampe_bleibt_gewoehnlich(self):
        self.assertEqual(self._getippt(LayerType.RAMP, 0.3, 0.7), (0.3, 0.7))

    def test_die_tastatur_verfolgung_ist_nur_bei_min_und_max_abgeschaltet(self):
        """★ Gegenprobe zum Umfang: bei den uebrigen Feldern ist ein
        Zwischenwert beim Tippen ein kurzes Flackern und korrigiert sich selbst.
        Nur bei min/max ist er ein Datenverlust, weil die Wache mitzieht.
        Pauschal abzuschalten waere eine Bedienaenderung ohne Befund."""
        eff, ed = self._editor(EffectLayer(type=LayerType.CLAMP))
        self._gewaehlt(ed, 0)
        self.assertFalse(ed._spin_min.keyboardTracking())
        self.assertFalse(ed._spin_max.keyboardTracking())
        for attr in ("amplitude", "frequency", "phase", "offset", "value",
                     "fixture_phase_step"):
            with self.subTest(feld=attr):
                self.assertTrue(ed._prop_rows[attr].keyboardTracking())


class DieFelderFolgenDerAUSWAHLTest(_EditorMixin, unittest.TestCase):
    """★★ Zweiter Skeptiker-Fund: ``_refresh`` uebergibt heute
    ``_current_layer()``, aber nichts hielt das fest.

    Die Mutation ``_sync_prop_rows(None)`` in ``_refresh`` ueberlebte — heute
    gleichwertig, weil ``_list.clear()`` die Zeile ohnehin auf -1 zurueckwirft.
    Festgenagelt war damit nur „ohne Auswahl alles ausblenden", nicht „auf die
    tatsaechliche Auswahl synchronisieren". Wer ``_refresh`` spaeter die Auswahl
    erhalten laesst — naheliegend, denn heute verliert ``_delete`` sie
    komplett —, raeumt mit der ``None``-Fassung die Felder still leer.
    """

    def test_refresh_synchronisiert_auf_die_tatsaechliche_auswahl(self):
        eff, ed = self._editor(EffectLayer(type=LayerType.RAMP))
        self._gewaehlt(ed, 0)
        # Die Auswahl-Auskunft festhalten, statt sich auf das heutige
        # Nebenverhalten von _list.clear() zu verlassen.
        ed._current_layer = lambda: eff.layers[0]
        ed._refresh()
        self.assertEqual(self._sichtbar(ed),
                         set(used_fields(LayerType.RAMP)),
                         "_refresh raeumt die Felder leer, obwohl eine Auswahl "
                         "besteht")
