"""FM-23 — QXF-Import leitet die Rasterform aus ``<Physical><Layout>`` ab.

**Die Frage des Items** war, ob ``qxf_import`` die Panel-Geometrie aus dem
Quellformat ABLEITEN kann. Antwort, gemessen am QLC+-Schema
(``resources/schemas/fixture.xsd``):

* **Ja fuer die Rasterform.** ``QLCPhysical`` fuehrt sie als
  ``<Layout Width= Height=/>``; ``<Physical>`` darf laut Schema unter
  ``<FixtureDefinition>`` UND unter ``<Mode>`` stehen. Die Angabe des Modus
  schlaegt die fixture-weite — genau wie in unserer Bibliothek, wo die
  Rasterform am Modus haengt, weil die Pixelzahl modusabhaengig ist.
* **Nein fuer die Weiss-Leiste.** Das Format kennt keinen Begriff fuer ein
  zweites Raster neben dem Farbraster: ``<Layout>`` beschreibt EIN Raster, ein
  ``<Head>`` ist eine Kanalgruppe ohne Ortsangabe. Aus den ``color_w``-Kanaelen
  liesse sie sich nicht schliessen — das war der Befund von CDX-52. Deshalb
  bleibt ``white_rows``/``white_cols`` beim Import 0, und diese Datei misst das
  ausdruecklich, statt es zu behaupten.

★★ ``1x1`` gilt als KEINE Angabe. QLC+ initialisiert ``m_layout`` mit
``QSize(1, 1)`` und schreibt das Element dann gar nicht erst (``qlcphysical.cpp``:
``if (layoutSize() != QSize(1, 1))``) — aus QLC+ selbst kommt ein ``1x1`` also
nicht; die Pruefung faengt handgeschriebene Profile und Konverter ab. Sie ist
nicht kosmetisch: ``panelGrid`` zieht die fehlende Zahl aus der Pixelzahl hoch
und markiert das Ergebnis als ``explizit`` — ein 48-Pixel-Modus mit
uebernommenem ``1x1`` waere eine 1 Spalte breite, 48 Zeilen hohe Saeule, und die
traegt dann auch noch die physischen Panel-Masse.

**Positivkontrolle** in jedem Abschnitt: eine echte Angabe muss ankommen, ein
Profil ohne Angabe muss unveraendert durchlaufen (Kanaele, Attribute, Watt), und
die Ableitung darf nichts beanstanden, was vorher funktionierte.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.database.models import Base, FixtureChannel, FixtureMode
from src.core.database.qxf_import import QXF_NS, import_qxf_file


def _qxf(model: str, *, fixture_physical: str = "", modes: str = "",
         typ: str = "LED Bar (Pixels)") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>{model}</Model>
 <Type>{typ}</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Channel Name="Blue" Preset="IntensityBlue"/>
 <Channel Name="White" Preset="IntensityWhite"/>
{fixture_physical}
{modes}
</FixtureDefinition>
"""


def _mode(name: str, physical: str = "") -> str:
    return f""" <Mode Name="{name}">
{physical}
  <Channel Number="0">Red</Channel>
  <Channel Number="1">Green</Channel>
  <Channel Number="2">Blue</Channel>
  <Channel Number="3">White</Channel>
 </Mode>"""


def _physical(inner: str) -> str:
    return f"""  <Physical>
   <Bulb Type="LED" Lumens="0" ColourTemperature="0"/>
   <Dimensions Weight="3" Width="1000" Height="200" Depth="120"/>
   <Technical PowerConsumption="60" DmxConnector="3-pin"/>
{inner}
  </Physical>"""


class _QxfFall(unittest.TestCase):

    def _import(self, xml_text: str) -> dict:
        """Importiert und liefert ``{modusname: ((gr, gc), (wr, wc))}``."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        fd, path = tempfile.mkstemp(suffix=".qxf")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml_text)
            with Session(engine) as s:
                self.assertTrue(import_qxf_file(path, s, {}),
                                "Import hat die Datei gar nicht angenommen")
                s.commit()
                modi = s.execute(select(FixtureMode)).scalars().all()
                self._kanaele = {
                    m.name: [(c.channel_number, c.name, c.attribute)
                             for c in s.execute(
                                 select(FixtureChannel)
                                 .where(FixtureChannel.mode_id == m.id)
                                 .order_by(FixtureChannel.channel_number)
                             ).scalars().all()]
                    for m in modi}
                return {m.name: ((m.grid_rows, m.grid_cols),
                                 (m.white_rows, m.white_cols)) for m in modi}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


# ════════════════════════════════════════════════════════════════════════════
# 1. Die Ableitung: <Layout> je Modus
# ════════════════════════════════════════════════════════════════════════════

class ModusLayoutTest(_QxfFall):

    def test_layout_des_modus_wird_zur_rasterform(self):
        """``Width`` sind SPALTEN, ``Height`` sind ZEILEN — vertauscht man das,
        steht das Panel hochkant."""
        modi = self._import(_qxf(
            "PanelMitLayout",
            modes=_mode("48ch", _physical('   <Layout Width="12" Height="4"/>'))))
        self.assertEqual(modi["48ch"], ((4, 12), (0, 0)))

    def test_jeder_modus_bekommt_sein_eigenes_layout(self):
        """★ Der Grund, warum die Angabe am Modus haengt: dasselbe Geraet zaehlt
        im einen Modus eine Zone und im anderen 48."""
        modi = self._import(_qxf(
            "PanelZweiModi",
            modes="\n".join([
                _mode("gross", _physical('   <Layout Width="12" Height="4"/>')),
                _mode("hoch", _physical('   <Layout Width="4" Height="12"/>')),
            ])))
        self.assertEqual(modi["gross"], ((4, 12), (0, 0)))
        self.assertEqual(modi["hoch"], ((12, 4), (0, 0)))


# ════════════════════════════════════════════════════════════════════════════
# 2. Rueckfallebene: fixture-weites <Physical>
# ════════════════════════════════════════════════════════════════════════════

class FixtureWeitesLayoutTest(_QxfFall):

    def test_fixture_weites_layout_gilt_fuer_modi_ohne_eigenes(self):
        """Aeltere QLC+-Dateien haben nur EIN ``<Physical>`` unter der Wurzel."""
        modi = self._import(_qxf(
            "PanelAltesFormat",
            fixture_physical=_physical('   <Layout Width="8" Height="2"/>'),
            modes=_mode("16ch")))
        self.assertEqual(modi["16ch"], ((2, 8), (0, 0)))

    def test_modus_layout_schlaegt_das_fixture_weite(self):
        modi = self._import(_qxf(
            "PanelBeides",
            fixture_physical=_physical('   <Layout Width="8" Height="2"/>'),
            modes="\n".join([
                _mode("eigen", _physical('   <Layout Width="12" Height="4"/>')),
                _mode("geerbt"),
            ])))
        self.assertEqual(modi["eigen"], ((4, 12), (0, 0)))
        self.assertEqual(modi["geerbt"], ((2, 8), (0, 0)))


# ════════════════════════════════════════════════════════════════════════════
# 3. Was NICHT als Angabe zaehlt
# ════════════════════════════════════════════════════════════════════════════

class KeineAngabeTest(_QxfFall):

    def test_ohne_layout_bleibt_es_bei_null(self):
        """``(0, 0)`` heisst „der Renderer raet weiter" — der Bestandsweg."""
        modi = self._import(_qxf("PanelOhneLayout", modes=_mode("4ch")))
        self.assertEqual(modi["4ch"], ((0, 0), (0, 0)))

    def test_einszueins_ist_der_vorgabewert_und_keine_angabe(self):
        """★★ Der Kern der Pruefung — s. Kopf dieser Datei."""
        modi = self._import(_qxf(
            "PanelEinsEins",
            modes=_mode("4ch", _physical('   <Layout Width="1" Height="1"/>'))))
        self.assertEqual(modi["4ch"], ((0, 0), (0, 0)))

    def test_dimensions_sind_gehaeusemasse_und_kein_raster(self):
        """``<Dimensions Width= Height=>`` steht im SELBEN ``<Physical>`` und
        traegt dieselben Attributnamen — in Millimetern. Wer danach greift,
        macht aus einem 1000 mm breiten Balken ein 1000-Spalten-Raster."""
        modi = self._import(_qxf("PanelNurDimensions",
                                 modes=_mode("4ch", _physical(""))))
        self.assertEqual(modi["4ch"], ((0, 0), (0, 0)))

    def test_kaputte_zahlen_werden_verworfen_nicht_geraten(self):
        modi = self._import(_qxf(
            "PanelKaputt",
            modes="\n".join([
                _mode("text", _physical('   <Layout Width="acht" Height="4"/>')),
                _mode("null", _physical('   <Layout Width="0" Height="4"/>')),
                _mode("leer", _physical('   <Layout/>')),
            ])))
        for name in ("text", "null", "leer"):
            self.assertEqual(modi[name], ((0, 0), (0, 0)), name)


# ════════════════════════════════════════════════════════════════════════════
# 4. Positivkontrolle: der Import bleibt im Uebrigen, wie er war
# ════════════════════════════════════════════════════════════════════════════

class ImportUnveraendertTest(_QxfFall):

    def test_kanaele_und_attribute_unveraendert_mit_layout(self):
        """Die Ableitung darf am eigentlichen Import nichts verschieben."""
        modi = self._import(_qxf(
            "PanelMitLayout2",
            modes=_mode("48ch", _physical('   <Layout Width="12" Height="4"/>'))))
        self.assertEqual(modi["48ch"], ((4, 12), (0, 0)))
        self.assertEqual(self._kanaele["48ch"], [
            (1, "Red", "color_r"), (2, "Green", "color_g"),
            (3, "Blue", "color_b"), (4, "White", "color_w"),
        ])

    def test_kanaele_und_attribute_unveraendert_ohne_layout(self):
        self._import(_qxf("PanelOhneLayout2", modes=_mode("4ch")))
        self.assertEqual(self._kanaele["4ch"], [
            (1, "Red", "color_r"), (2, "Green", "color_g"),
            (3, "Blue", "color_b"), (4, "White", "color_w"),
        ])

    def test_datei_ohne_mode_element_bekommt_das_fixture_weite_layout(self):
        """Der Sonderweg „kein ``<Mode>``, alle Kanaele als Standard" darf nicht
        stillschweigend leer ausgehen — genau solche uebersprungenen Zweige sind
        in diesem Projekt schon mehrfach als gruene Luecke aufgefallen."""
        modi = self._import(_qxf(
            "PanelOhneModes",
            fixture_physical=_physical('   <Layout Width="2" Height="2"/>')))
        self.assertEqual(modi["Standard"], ((2, 2), (0, 0)))


if __name__ == "__main__":
    unittest.main()
