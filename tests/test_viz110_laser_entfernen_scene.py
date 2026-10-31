"""VIZ-110: ein geloeschter bewegter Laser meldet sich aus der Eigenbewegung ab.

Ein Laser mit Eigenbewegung (dx/dy/dz/dr, VIZ-79) steht in ``_bewegt``
(fixtures/laser.js); solange dort ein sichtbarer Eintrag steht, haelt die
Live-Probe ``laserAnimationAktiv`` den Render-Loop wach. ``removeFixture``
raeumte diesen Eintrag nicht ab — erst ``tickLaserAnimation`` im naechsten
Bild warf ihn hinaus. Bis dahin meldete die Probe einen Laser, den es nicht
mehr gibt (gleiche Luecke wie VIZ-90 beim Spot-Pool).

Gemessen ueber ``renderStats().live`` direkt nach ``fixtureRemoved`` — ohne
dazwischen ein Bild zu ticken. Dazu die Gegenproben fuer den Neubau mit
gleicher fid: ohne DMX-Stand steht der neue Laser still, mit bewegtem
DMX-Stand laeuft er weiter (das ist der Stand des neuen Geraets, kein Erbe).
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

import test_viz79_laser_strahlen_scene as _v79  # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@pytest.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_FID = _v79._FID
_BEWEGT = {"dx": True, "tempo": 0.2}


class Viz110LaserEntfernenSceneTest(_v79.Viz79LaserMusterSceneTest):
    """Geerbt werden nur Aufbau und Helfer der VIZ-79-Szenentests."""


# Die geerbten VIZ-79-Tests laufen in ihrer eigenen Datei.
for _name in [n for n in dir(_v79.Viz79LaserMusterSceneTest) if n.startswith("test_")]:
    setattr(Viz110LaserEntfernenSceneTest, _name, None)


def _stats(self):
    return json.loads(self._eval("JSON.stringify(window.__lightos.renderStats())"))


def _bewegter_laser(self):
    self._load_and_wait()
    self._eval("window.__lightos.setViewMode('3D');"
               " window.__lightos.settings.showCones = true; true")
    self._bauen(_v79._laser())
    self._apply([_v79._gruen(laser=_BEWEGT)], 1)
    i = self._info()
    self.assertTrue(i["bewegt"] and i["animationAktiv"],
                    "Vorbedingung: bewegter Laser nicht als animiert gemeldet")


def test_entfernen_meldet_den_laser_sofort_ab(self):
    _bewegter_laser(self)
    self._bridge_obj.fixtureRemoved.emit(_FID)
    self._poll_until_true("!window.__lightos.fixtures['%d']" % _FID)
    # Kein Bild dazwischen: die Live-Probe darf den geloeschten Laser
    # nicht mehr melden.
    self.assertFalse(_stats(self)["live"],
                     "geloeschter bewegter Laser haelt den Render-Loop wach")


def test_neubau_gleicher_fid_ohne_dmx_steht_still(self):
    _bewegter_laser(self)
    self._bridge_obj.fixtureRemoved.emit(_FID)
    self._poll_until_true("!window.__lightos.fixtures['%d']" % _FID)
    self._bauen(_v79._laser())
    i = self._info()
    self.assertFalse(i["bewegt"] or i["animationAktiv"],
                     "neu gebauter Laser erbt die Bewegung des geloeschten")
    self.assertFalse(_stats(self)["live"])


def test_neubau_mit_bewegtem_dmx_laeuft_weiter(self):
    """Gegenprobe: ``addFixture`` ueber einen bestehenden Laser (Resync,
    gleiche Liste) baut mit dem letzten DMX-Stand — der bewegt weiter."""
    _bewegter_laser(self)
    self._bridge_obj.allFixtures.emit(json.dumps([_v79._laser(x=0.5)]))
    self._poll_until_true(
        "window.__lightos.fixtures['%d'] && window.__lightos.fixtures['%d'].data.x === 0.5"
        % (_FID, _FID))
    i = self._info()
    self.assertTrue(i["bewegt"] and i["animationAktiv"],
                    "Neubau mit bewegtem DMX-Stand steht still")


Viz110LaserEntfernenSceneTest.test_entfernen_meldet_den_laser_sofort_ab = \
    test_entfernen_meldet_den_laser_sofort_ab
Viz110LaserEntfernenSceneTest.test_neubau_gleicher_fid_ohne_dmx_steht_still = \
    test_neubau_gleicher_fid_ohne_dmx_steht_still
Viz110LaserEntfernenSceneTest.test_neubau_mit_bewegtem_dmx_laeuft_weiter = \
    test_neubau_mit_bewegtem_dmx_laeuft_weiter
del test_entfernen_meldet_den_laser_sofort_ab
del test_neubau_gleicher_fid_ohne_dmx_steht_still
del test_neubau_mit_bewegtem_dmx_laeuft_weiter
