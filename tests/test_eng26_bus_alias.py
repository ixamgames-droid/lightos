"""ENG-26: ``ensure_bus("Global")`` und ``get("Global")`` meinen denselben Bus.

``TempoBusManager.get`` loest ``""``/``"default"``/``"global"`` (case-insensitiv)
auf den Default-Bus auf. ``ensure_bus`` tat das **nicht** und legte fuer jede
Schreibweise einen eigenen Bus an.

★ **Gemessen, bevor gebaut wurde** (das Item trug „Verdacht, Erreichbarkeit noch
nicht belegt"): sechs Aufrufe erzeugten sechs Buses — ``'Global'``,
``'global'``, ``'GLOBAL'``, ``'Default'``, ``' global '`` neben dem echten
``'default'``.

⚠️ **Und es ist erreichbar, nicht theoretisch.** ``"Global"`` ist der DEFAULT von
``Function.tempo_bus_id`` fuer alle taktgebundenen Subtypen und steht in vier
Editor-Dropdowns zur Auswahl. Ein Speed-Knoten mit dieser id steuerte ueber
``vc_speedial._node_bus`` (``ensure_bus``) einen Bus, den kein Effekt liest —
waehrend die Anzeige daneben (``:177``, ``get``) den richtigen zeigte. Zwei
Zahlen, die dasselbe behaupten und es nicht sind.

★★ **Der Fix hat eine zweite Haelfte, die beim Messen auffiel.** Sobald
``ensure_bus`` den Alias aufloest, rutscht ein im BPM-Fenster getipptes
„Global" durch die Wache von ``_on_add_master`` (die nur den woertlichen
``DEFAULT_BUS`` abwies) und liefert den Default-Bus zurueck. Die Wache prueft
jetzt ebenfalls kanonisch. Beide Haelften haengen an derselben Funktion, damit
sie nicht wieder auseinanderlaufen.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.tempo_bus import TempoBusManager

#: Jede Schreibweise, die den Default-Bus meint.
ALIASE = ("Global", "global", "GLOBAL", "Default", "default", " global ", "", None)


class AliasTest(unittest.TestCase):
    def setUp(self):
        self.m = TempoBusManager()

    def test_ensure_bus_und_get_liefern_denselben_bus(self):
        """Das Abnahmekriterium des Items, woertlich."""
        for alias in ALIASE:
            with self.subTest(alias=alias):
                self.assertIs(self.m.ensure_bus(alias), self.m.get(alias),
                              f"{alias!r} erzeugt einen zweiten Bus neben dem "
                              f"Default — kein Effekt liest ihn")

    def test_kein_alias_erzeugt_einen_zweiten_bus(self):
        """★ Die Zaehlung, nicht nur die Identitaet.

        Vorher standen nach genau diesen Aufrufen sechs Buses in der Liste. Ein
        Test nur auf ``is`` haette einen Phantom-Bus uebersehen, der zusaetzlich
        entsteht, ohne zurueckgegeben zu werden.
        """
        for alias in ALIASE:
            self.m.ensure_bus(alias)
        self.assertEqual([self.m.DEFAULT_BUS], sorted(self.m._buses),
                         "es sind Phantom-Buses entstanden")

    def test_ein_echter_name_erzeugt_weiterhin_einen_bus(self):
        """★★ Die Gegenprobe: die Aufloesung darf nicht alles verschlucken."""
        b = self.m.ensure_bus("Buehne links")
        self.assertEqual("Buehne links", b.bus_id)
        self.assertIn("Buehne links", self.m._buses)

    def test_ein_name_der_nur_so_ANFAENGT_wird_nicht_verschluckt(self):
        """★ Die Grenze: ``"Globalstrahler"`` ist kein Alias.

        Ein Praefix-Vergleich statt eines Gleichheits-Vergleichs waere hier
        nicht auffaellig — beide Namen fangen gleich an, und der Bus verschwaende
        stillschweigend im Default.
        """
        for name in ("Globalstrahler", "Global 2", "defaults", "Vorglobal"):
            with self.subTest(name=name):
                self.assertEqual(name, self.m.ensure_bus(name).bus_id)
                self.assertIsNot(self.m.ensure_bus(name), self.m.get(""))

    def test_die_kanonische_form_ist_die_EINE_quelle(self):
        for alias in ALIASE:
            with self.subTest(alias=alias):
                self.assertEqual(self.m.DEFAULT_BUS,
                                 self.m.kanonische_bus_id(alias))


class ErreichbarkeitTest(unittest.TestCase):
    """⚠️ Warum das kein theoretischer Fall ist — die Praemisse festgenagelt.

    Faellt dieser Test, weil ``Function`` seinen Default aendert, ist ENG-26
    nicht mehr erreichbar; dann soll man es hier erfahren und nicht raten.
    """

    def test_taktgebundene_funktionen_tragen_Global_als_default(self):
        from src.core.engine.function import Function

        class _Takt(Function):
            tempo_sync_default = True

        class _Statisch(Function):
            tempo_sync_default = False

        self.assertEqual("Global", _Takt(name="t").tempo_bus_id,
                         "der Default ist nicht mehr 'Global' — dann ist die "
                         "Alias-Falle aus ENG-26 nicht mehr erreichbar")
        self.assertEqual("", _Statisch(name="s").tempo_bus_id,
                         "statische Funktionen laufen frei, nicht auf Default")

    def test_dieser_default_traf_frueher_einen_leeren_bus(self):
        """★★ Der Fehler in einem Satz: derselbe Wert, zwei Antworten.

        Vor dem Fix lieferten ``get`` und ``ensure_bus`` fuer die
        VOREINGESTELLTE Bus-id verschiedene Objekte — die Anzeige las den
        richtigen, der Speed-Knoten steuerte den anderen.
        """
        m = TempoBusManager()
        from src.core.engine.function import Function

        class _Takt(Function):
            tempo_sync_default = True

        bid = _Takt(name="t").tempo_bus_id
        self.assertIs(m.get(bid), m.ensure_bus(bid))


class WacheImBpmFensterTest(unittest.TestCase):
    """Die zweite Haelfte: ``_on_add_master`` weist auch die Aliase ab.

    Ohne Qt geprueft — die Wache haengt allein an
    :meth:`TempoBusManager.kanonische_bus_id`, und genau diese Bindung ist das,
    was nicht wieder auseinanderlaufen darf.
    """

    def test_die_wache_erkennt_jeden_alias_als_default(self):
        m = TempoBusManager()
        for name in ("Global", " global ", "DEFAULT"):
            with self.subTest(name=name):
                self.assertEqual(m.DEFAULT_BUS, m.kanonische_bus_id(name),
                                 "die Wache im BPM-Fenster laesst diesen Namen "
                                 "durch und legt still den Default-Bus an")

    def test_und_laesst_echte_namen_durch(self):
        m = TempoBusManager()
        self.assertNotEqual(m.DEFAULT_BUS, m.kanonische_bus_id("Buehne links"))


if __name__ == "__main__":
    unittest.main()
