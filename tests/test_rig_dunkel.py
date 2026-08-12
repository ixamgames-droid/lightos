"""RIG-DUNKEL — im grossen Test-Rig wurden sechs Geraete nie hell.

★ **Gefunden vom Dimmer-Waechter aus TOOL-SMOKEDIM, im ersten Einsatz.** Und
der eigentliche Grund, warum es niemandem auffiel, steckte eine Ebene tiefer:
``build_grosses_rig.py`` rief ``build_and_verify`` **ohne** ``render=`` — fuer
dieses Rig lief also weder der Render-Smoke noch der Dimmer-Waechter. Es hat
schlicht nie jemand nachgesehen.

Zwei verschiedene Fehler kamen zusammen:

1. **Die vier Moving Heads haben gar kein RGB.** Ihr 8-Kanal-Modus ist
   ``['pan','tilt','color_wheel','gobo_wheel','intensity','shutter','speed',
   'macro']``. Der RGB-Matrix-Effekt „MH ColorFade" fand dort keine Kanaele und
   erzeugte **null** DMX-Aenderungen — gemessen. Ein Effekt, der seit jeher in
   der Show stand und nie irgendetwas getan hat.
2. **Die Spider faerbten, blieben aber dunkel.** Ihr Farbeffekt lief ohne
   ``drive_intensity`` und liess den Master-Dimmer auf 0 — genau der Fall vom
   2026-08-05.

Dieser Test haelt beides fest: an den PROFILEN (damit ein RGB-Effekt fuer ein
Farbrad-Geraet nicht zurueckkommt) und an der GEBAUTEN Show (damit jedes
gepatchte Geraet waehrend der Probe wirklich hell wird).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _rig_bauen():
    """Das echte Build-Skript fahren und den Builder abfangen.

    Gebaut wird die WIRKLICHE Show — eine nachgebaute waere wertlos, weil
    genau die Abweichung zwischen Skript und Annahme der Fehler war.
    """
    import importlib.util
    import sys
    sys.path.insert(0, "tools")
    import _builder

    gefangen = {}
    echt = _builder.build_and_verify

    def abfangen(builder, out, **kw):
        gefangen["builder"], gefangen["kw"] = builder, kw
        return out

    spec = importlib.util.spec_from_file_location(
        "_rig_unter_test", "tools/build_grosses_rig.py")
    modul = importlib.util.module_from_spec(spec)
    _builder.build_and_verify = abfangen
    try:
        spec.loader.exec_module(modul)
        modul.build_and_verify = abfangen
        try:
            modul.main()
        except SystemExit:
            pass
    finally:
        _builder.build_and_verify = echt
    return gefangen


class ProfileTest(unittest.TestCase):
    """Die Voraussetzung, aus der der Fehler folgte."""

    def test_moving_head_hat_ein_farbrad_und_kein_rgb(self):
        """Ein RGB-Effekt kann an diesem Geraet nichts bewirken — das ist der
        Grund, warum „MH ColorFade" null Kanaele schrieb."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database import fixture_db as fdb
        from src.core.database.models import FixtureProfile

        with Session(fdb.engine()) as s:
            prof = s.scalars(select(FixtureProfile)
                             .where(FixtureProfile.short_name == "MH8")).first()
            self.assertIsNotNone(prof, "Profil MH8 fehlt")
            attrs = {c.attribute for m in prof.modes for c in m.channels}
        self.assertIn("color_wheel", attrs)
        self.assertIn("intensity", attrs)
        self.assertNotIn("color_r", attrs,
                         "Wenn der MH RGB bekaeme, waere ein RGB-Effekt wieder "
                         "sinnvoll — dann gehoert dieser Test angepasst.")


class GebauteShowTest(unittest.TestCase):
    """★ Der eigentliche Beleg: jedes gepatchte Geraet wird waehrend der Probe
    wirklich hell."""

    @classmethod
    def setUpClass(cls):
        cls.gefangen = _rig_bauen()
        cls.builder = cls.gefangen.get("builder")

    def test_das_skript_faehrt_ueberhaupt_einen_render_smoke(self):
        """Ohne `render=` laufen weder Smoke noch Dimmer-Waechter — das war der
        Grund, warum sechs dunkle Geraete jahrelang unbemerkt blieben."""
        self.assertIsNotNone(self.builder, "Build-Skript nicht ausgefuehrt")
        self.assertTrue(self.gefangen["kw"].get("render"),
                        "build_and_verify wird ohne render= gerufen — dann "
                        "prueft niemand, ob die Show ueberhaupt Licht macht")

    def test_die_probe_deckt_einen_ganzen_chaser_durchlauf_ab(self):
        """Sonst meldet der Waechter die hinteren Geraete des Lauflichts als
        dunkel — ein Fehlalarm, der ihn auf Dauer unbrauchbar macht."""
        frames = self.gefangen["kw"].get("frames", 44)
        self.assertGreaterEqual(
            frames, 93,
            "6 Schritte a 0,35 s = 2,1 s = 93 Frames; mit weniger werden die "
            "hinteren PARs nie hell")

    def test_kein_geraet_bleibt_dunkel(self):
        """★★ Die Fertig-Bedingung des Items, an der ECHTEN Show gemessen."""
        from src.core.capability.dimmer_check import dunkle_geraete
        from src.core.capability.render_probe import render_diff

        fids = [int(h) for h in self.gefangen["kw"]["render"]]
        _lit, _moved, _ch, probe = render_diff(
            self.builder.state, fids, universe=1,
            frames=self.gefangen["kw"].get("frames", 44), return_snapshot=True)
        meldungen = dunkle_geraete(self.builder.state, probe.hoechstwert,
                                   universe=1)
        self.assertEqual([], list(meldungen),
                         "Diese Geraete bleiben in der gebauten Show dunkel:\n"
                         + "\n".join(meldungen))

    def test_jede_gepruefte_funktion_erzeugt_dmx(self):
        """Positivkontrolle gegen den zweiten Fehler: ein Effekt, der zum Geraet
        nicht passt (RGB auf Farbrad), erzeugt gar nichts — und faellt hier
        durch, bevor jemand ihn im 3D sucht."""
        from src.core.capability.render_probe import render_diff

        stumm = []
        for h in self.gefangen["kw"]["render"]:
            fid = int(h)
            lit, moved, changed = render_diff(
                self.builder.state, [fid], universe=1,
                frames=self.gefangen["kw"].get("frames", 44))
            if not (lit or moved):
                stumm.append(fid)
        self.assertEqual([], stumm,
                         f"Diese Funktionen erzeugen KEIN DMX: {stumm}")


if __name__ == "__main__":
    unittest.main()
