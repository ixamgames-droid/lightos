"""FM-17: „Kopf N“ muss den Kanal von Kopf N treffen — und sichtbar werden.

Der Befund kam aus der Review zu FM-9/A8 und ist an der ``HYDRA4000 19-Kanal``
gemessen: die Kopf-Zuordnung zaehlte VORKOMMEN eines Attributs, nicht Koepfe.
Das Geraet legt seine fuenf Intensity-Kanaele als ``CH1 Master Dimmer`` +
``CH9/12/15/18 Kopf 1..4 Dimmer`` an — „Kopf 2“ landete damit auf dem ZWEITEN
Vorkommen = CH9 = **Kopf 1**, und „Kopf 1“ auf dem gemeinsamen Master, dimmte
also das ganze Geraet.

Gemessen wurde ausserdem, was die Backlog-Zeile noch nicht wusste: der Master
steht per ``default_value`` auf 0. Ein Kopf-Dimmer allein macht deshalb GAR KEIN
Licht — die Fehlzuordnung war unsichtbar, weil ueberhaupt nichts leuchtete.
Beides gehoert zusammen; ein Fix, der den richtigen Kanal trifft und das Geraet
dunkel laesst, waere aus Davids Sicht keiner.

Drei Geraeteformen decken den Vertrag ab (alle aus der EINGEBAUTEN Library —
kein Profil aus Davids importierter 10-MB-DB, sonst ist die CI rot):

* ``HYDRA4000 19-Kanal`` — geteilter Master + je Kopf ein Dimmer (der Fehlerfall),
* ``HYDRA4000 56-Kanal`` — je Kopf ein Dimmer, KEIN Master (war korrekt, bleibt es),
* ``MOVBAR4 22-Kanal``   — NUR ein Master, kein Kopf-Dimmer (Kopf-Schreiben
  verschwand bisher spurlos: der Schluessel ``intensity#1`` gehoert keinem Kanal).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import (
    channel_occurrence_keys, channels_for_head, get_channels_for_patched,
    get_state, head_channel_map, programmer_key_for_head,
    shared_master_channels,
)
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import (
    FixtureMode, FixtureProfile, PatchedFixture,
)
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mode(short_name: str, mode_part: str):
    """(profil_id, modus_name, kanalzahl) eines EINGEBAUTEN Profils."""
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short_name)).scalars().first())
        for m in s.execute(select(FixtureMode).where(
                FixtureMode.fixture_id == pid)).scalars():
            if mode_part in m.name:
                return pid, m.name, int(m.channel_count)
    raise AssertionError(f"Eingebauter Modus {short_name}/{mode_part} fehlt")


class HeadDimmerMapTest(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _patch(self, short_name: str, mode_part: str, fid: int = 1):
        pid, mname, ccount = _mode(short_name, mode_part)
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"{short_name} {mode_part}", fixture_profile_id=pid,
            mode_name=mname, channel_count=ccount, universe=1, address=1))
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == fid)
        return fx, get_channels_for_patched(fx)

    def _dmx(self, fx, channel_number: int) -> int:
        return self.state.universes[fx.universe].get_channel(
            fx.address + channel_number - 1)

    def _named(self, channels, name: str) -> int:
        """Kanalnummer ueber den Anzeigenamen — macht die Zusagen lesbar."""
        for c in channels:
            if (c.name or "") == name:
                return int(c.channel_number)
        raise AssertionError(f"Kanal {name!r} fehlt: "
                             f"{[c.name for c in channels]}")

    # ── Die Karte selbst ────────────────────────────────────────────────────

    def test_kopf_karte_trennt_master_von_kopf_dimmern(self):
        _fx, chans = self._patch("HYDRA4000", "19-Kanal")
        per_head = head_channel_map(chans)["intensity"]
        namen = [chans[i].name for i in per_head]
        self.assertEqual(
            namen, ["Kopf 1 Dimmer", "Kopf 2 Dimmer",
                    "Kopf 3 Dimmer", "Kopf 4 Dimmer"],
            "Die Kopf-Karte muss die vier Kopf-Dimmer treffen, nicht den Master")
        self.assertEqual(
            [c.name for c in shared_master_channels(chans, "intensity")],
            ["Master Dimmer"], "Der Master gehoert KEINEM Kopf")

    def test_karte_gilt_bewusst_nur_fuer_dimmer(self):
        """Die Segment-Regel wuerde ueber die ganze Library 128 Zuordnungen
        verschieben — gemessen falsch waren aber nur die 27 Intensity-Faelle.
        Alles andere bleibt beim Vorkommens-Zaehlen, aus zwei belegten Gruenden:
        bei einigen Profilen wandern ``color_g``/``color_b``, nicht aber
        ``color_r`` (der Anker) — Rot und Blau eines Kopfes kaemen dann von
        verschiedenen Koepfen; und 7 Laser-Modi bekaemen eine Karte auf
        ``macro``/``color_wheel``, also auf Muster- und Betriebsart-Kanaelen."""
        _fx, chans = self._patch("HYDRA4000", "19-Kanal")
        self.assertEqual(sorted(head_channel_map(chans)), ["intensity"])
        self.assertEqual(
            programmer_key_for_head(chans, "shutter", 1), "shutter",
            "geteiltes Strobe: einmaliges Vorkommen -> gemeinsamer Kanal")

    def test_bewegungsachse_bleibt_unveraendert(self):
        """Pan/Tilt sind die Kopf-ANKER — ihre Zuordnung kann sich nie
        verschieben. Das ist die Garantie, dass EFX und XY-Pad unberuehrt
        bleiben."""
        _fx, chans = self._patch("HYDRA4000", "19-Kanal")
        for attr in ("pan", "tilt"):
            for head in range(4):
                self.assertEqual(
                    programmer_key_for_head(chans, attr, head),
                    attr if head == 0 else f"{attr}#{head}",
                    f"{attr}: Kopf {head} darf nicht wandern")

    def test_speicherformat_unveraendert_keine_show_migration(self):
        """``channel_occurrence_keys`` ist der Vertrag zwischen gespeicherten
        Shows und Kanaelen. FM-17 verschiebt NUR, welchen Schluessel ein Kopf
        adressiert — nicht, welchen Kanal ein Schluessel trifft. Genau deshalb
        braucht der Fix keine Show-Migration."""
        _fx, chans = self._patch("HYDRA4000", "19-Kanal")
        keys = {c.name: k for c, k in channel_occurrence_keys(chans)}
        self.assertEqual(keys["Master Dimmer"], "intensity")
        self.assertEqual(keys["Kopf 1 Dimmer"], "intensity#1")
        self.assertEqual(keys["Kopf 4 Dimmer"], "intensity#4")

    # ── Der Schreibweg, ueber ALLE Flaechen derselbe ────────────────────────

    def test_kopf_2_dimmen_trifft_kopf_2_und_macht_licht(self):
        """Das Akzeptanzkriterium aus dem Backlog — plus die Haelfte, die erst
        die Messung gezeigt hat: der geteilte Master muss aufgehen."""
        fx, chans = self._patch("HYDRA4000", "19-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 128, head=1)

        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 2 Dimmer")), 128,
                         "„Kopf 2“ muss auf dem Dimmer von Kopf 2 landen")
        self.assertEqual(self._dmx(fx, self._named(chans, "Master Dimmer")), 128,
                         "ohne offenen Master bleibt der Kopf dunkel")
        for anderer in ("Kopf 1 Dimmer", "Kopf 3 Dimmer", "Kopf 4 Dimmer"):
            self.assertEqual(
                self._dmx(fx, self._named(chans, anderer)), 0,
                f"{anderer} darf NICHT mitgezogen werden")

    def test_kopf_1_ist_ein_kopf_und_nicht_das_ganze_geraet(self):
        fx, chans = self._patch("HYDRA4000", "19-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 200, head=0)
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 1 Dimmer")), 200)
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 2 Dimmer")), 0)

    def test_geraeteweit_bleibt_geraeteweit(self):
        """``head=None`` = ganzes Geraet: Master gesetzt, alle Koepfe spiegeln
        ihn ueber den Flush-Fallback. Byte-identisch zum Bestand."""
        fx, chans = self._patch("HYDRA4000", "19-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 90)
        for name in ("Master Dimmer", "Kopf 1 Dimmer", "Kopf 2 Dimmer",
                     "Kopf 3 Dimmer", "Kopf 4 Dimmer"):
            self.assertEqual(self._dmx(fx, self._named(chans, name)), 90, name)

    def test_geteilter_dimmer_ohne_kopf_kanal_verschwindet_nicht_mehr(self):
        """MOVBAR4: vier Bewegungskoepfe, aber nur EIN Dimmer. Bisher schrieb
        „Kopf 2“ den Schluessel ``intensity#1``, den kein Kanal traegt — der Wert
        landete im Programmer und NIE auf DMX. Betrifft 358 Modi der Library."""
        fx, chans = self._patch("MOVBAR4", "22-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 77, head=1)
        self.assertEqual(self._dmx(fx, self._named(chans, "Master Dimmer")), 77)

    def test_geteilte_farbe_erreicht_den_gemeinsamen_kanal(self):
        """Dieselbe Falle in Farbe: die 19-Kanal-Hydrabeam hat EINE RGBW-Bank
        fuer alle vier Koepfe. Ein Kopf-Ziel muss sie treffen statt ins Leere zu
        schreiben."""
        fx, chans = self._patch("HYDRA4000", "19-Kanal")
        self.state.set_programmer_value(fx.fid, "color_r", 210, head=2)
        self.assertEqual(self._dmx(fx, self._named(chans, "Rot")), 210)

    def test_geraet_ohne_master_bleibt_wie_es_war(self):
        """56-Kanal: je Kopf ein Dimmer, kein gemeinsamer Master. Hier war die
        alte Zaehlung schon richtig — sie muss es bleiben, und es darf KEIN
        Master mitgezogen werden (es gibt keinen)."""
        fx, chans = self._patch("HYDRA4000", "56-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 111, head=1)
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 2 Dimmer")), 111)
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 1 Dimmer")), 0)
        self.assertEqual(
            programmer_key_for_head(chans, "intensity", 0), "intensity",
            "ohne geteilten Master ist Kopf 1 unveraendert der Basis-Schluessel")

    def test_zwei_koepfe_nacheinander_bleiben_unabhaengig(self):
        fx, chans = self._patch("HYDRA4000", "19-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 60, head=0)
        self.state.set_programmer_value(fx.fid, "intensity", 240, head=3)
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 1 Dimmer")), 60)
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 4 Dimmer")), 240)
        self.assertEqual(self._dmx(fx, self._named(chans, "Master Dimmer")), 240,
                         "der geteilte Master folgt dem hellsten Kopf")
        self.assertEqual(self._dmx(fx, self._named(chans, "Kopf 2 Dimmer")), 0)

    def test_lesen_und_schreiben_benutzen_denselben_schluessel(self):
        """Ein Regler, der anders liest als er schreibt, springt beim Neubau
        zurueck. Deshalb faehrt get_programmer_value dieselbe Aufloesung."""
        fx, _chans = self._patch("HYDRA4000", "19-Kanal")
        self.state.set_programmer_value(fx.fid, "intensity", 33, head=2)
        self.assertEqual(
            self.state.get_programmer_value(fx.fid, "intensity", head=2), 33)

    # ── Projektion (Matrix/EFX) ────────────────────────────────────────────

    def test_projektion_gibt_dem_kopf_seinen_eigenen_dimmer(self):
        _fx, chans = self._patch("HYDRA4000", "19-Kanal")
        proj = channels_for_head(chans, 1)
        self.assertEqual(proj["intensity"].name, "Kopf 2 Dimmer")
        self.assertEqual(proj["pan"].name, "Kopf 2 Pan",
                         "die Bewegungsachse bleibt, wo sie war")
        self.assertEqual(proj["color_r"].name, "Rot",
                         "die geteilte Farbe erscheint bei jedem Kopf")


if __name__ == "__main__":
    unittest.main()
