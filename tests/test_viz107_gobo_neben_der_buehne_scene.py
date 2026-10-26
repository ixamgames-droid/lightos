"""VIZ-107 — die Strahlmitte liegt NEBEN der Buehne, der Kegel trifft sie noch.

Laeuft in der seriellen Spur der QWebEngineView-Dateien (echte Seite). Zweite
Haelfte zu ``test_viz107_gobo_kante_stetig_scene.py`` (dort: der gemeldete Fall,
ein Geraet ueber der Buehne schwenkt ueber die Kante auf den Hallenboden).

Hier die Faelle, die eine Review des ersten Stands gefunden hat — in jedem
verschwand der Teil des Musters auf der Buehne weiter in einem Schritt:

* **Publikumsflaeche vor der Buehne** (so ist die Demo „Große Bühnen-Show“
  gebaut): die Strahlmitte landet auf einer tieferen Oberseite, nicht auf dem
  Hallenboden.
* **Geraet vor der Buehne**: zwischen Boden und Oberseite trifft die
  Strahlmitte einige Schritte lang die Stirnseite.
* **Zweiter, hoeherer Koerper**: er gewann, sobald der Kegel ihn beruehrte.
* **Ecke**: der Anteil auf der Buehne wurde nur in acht Richtungen geprueft.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_viz96_gobo_projektion_scene import _RING, _geraet     # noqa: E402
from test_viz107_gobo_kante_stetig_scene import (                # noqa: E402,F401
    _KANTE_Z, _OBEN, _KanteBasis, _auf_der_buehne,
    _xplat15_no_leaked_widgets)


def _stetig(test, reihe, schluessel="tilt"):
    """Gemeinsame Pruefung einer Fahrt: Kegelweite, Lage und Helligkeit des
    Musterteils am Auftreffpunkt der Strahlmitte aendern sich je Schritt nur
    wenig."""
    weite = [z["durchmesser"] for z in reihe]
    rel = [abs(b - a) / a for a, b in zip(weite, weite[1:])]
    test.assertLess(max(rel), 0.06,
                    f"Kegelweite springt: {[(z[schluessel], round(w, 2)) for z, w in zip(reihe, weite)]}")
    # Der Teil an der Strahlmitte: die zweite Scheibe, sonst die erste.
    unten = [(z[schluessel], z["zwei"] or z["eins"]) for z in reihe]
    for (a, p), (b, q) in zip(unten, unten[1:]):
        weg = ((q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2) ** 0.5
        test.assertLess(weg, 0.6, f"Muster springt zwischen {a} und {b}: {p} -> {q}")
        test.assertLess(abs(q[1] - p[1]), 0.1, f"Muster wechselt die Hoehe zwischen {a} und {b}")
    hell = [(z[schluessel], (z["zweiDeck"] / z["einsDeck"]) if z["zwei"] else 1.0)
            for z in reihe if z["einsDeck"] > 0]
    for (a, h), (b, k) in zip(hell, hell[1:]):
        test.assertLess(abs(k - h), 0.2, f"Helligkeit springt zwischen {a} und {b}: {h:.2f} -> {k:.2f}")


class Viz107PublikumTest(_KanteBasis):
    """Die Buehne der Demo „Große Bühnen-Show“: vor der Buehne ein Streifen
    Hallenboden, dann eine 5 cm hohe Publikumsflaeche. Dort landet die
    Strahlmitte nach der Kante nicht auf dem Boden, sondern auf einer TIEFEREN
    Oberseite — und die brachte ihre eigene Kante mit: der Teil auf der Buehne
    verschwand, sobald die Mitte die Publikumsflaeche erreichte."""
    TIER = "low"
    TILTS = list(range(128, 91, -1))

    def _hin(self):
        self._start()
        # 12 x 0,05 x 8 m, beginnt 2 m vor der Buehnenkante.
        self._flaeche("publikum", "audience", (0, 0.025, _KANTE_Z + 2 + 4), (12, 0.05, 8))
        return self._fahrt(self.TILTS, gobo_wheel=_RING)

    def test_teil_auf_der_buehne_bleibt_ueber_streifen_und_publikumsflaeche(self):
        reihe = self._hin()
        mitte = ["buehne" if (z["mitteOben"] and abs(z["ziel"][1] - _OBEN) < 1e-6)
                 else ("publikum" if z["mitteOben"] else "boden") for z in reihe]
        self.assertEqual(mitte[0], "buehne")
        self.assertIn("boden", mitte, "Aufbau: die Fahrt ueberquert den Bodenstreifen")
        self.assertEqual(mitte[-1], "publikum", "Aufbau: die Fahrt endet auf der Publikumsflaeche")
        erster = mitte.index("publikum")
        self.assertGreaterEqual(len(mitte) - erster, 4)
        for z, wo in zip(reihe, mitte):
            with self.subTest(tilt=z["tilt"], mitte=wo):
                self.assertTrue(_auf_der_buehne(z), f"Teil auf der Buehne verschwunden: {z}")
                self.assertTrue(z["einsGeschnitten"])
                if wo != "buehne":
                    self.assertEqual(z["neben"], "podest")
                    # die zweite Scheibe liegt auf der Flaeche der Strahlmitte
                    self.assertAlmostEqual(z["zwei"][1], z["ziel"][1] + 0.01, places=6)
        self.assertAlmostEqual(reihe[erster]["zwei"][1], 0.06, places=6)

    def test_kein_sprung_an_der_publikumsflaeche(self):
        _stetig(self, self._hin())


class Viz107VorDerBuehneTest(_KanteBasis):
    """Das Geraet haengt VOR der Buehne (Front-Traverse) und sieht ihre
    Vorderseite. Zwischen „Mitte am Boden“ und „Mitte auf der Buehne“ trifft
    die Strahlmitte ein paar Schritte lang die Stirnseite — auch dort bleibt
    die Anordnung stehen."""
    TIER = "low"
    GERAETE = [_geraet(tiltRange=270, z=_KANTE_Z + 3)]
    TILTS = list(range(128, 162))

    def _hin(self):
        self._start()
        reihe = self._fahrt(self.TILTS, gobo_wheel=_RING)
        wo = ["oben" if z["mitteOben"] else ("seite" if z["mitteSeite"] else "boden")
              for z in reihe]
        return reihe, wo

    def test_boden_stirnseite_oberseite_in_dieser_reihenfolge(self):
        reihe, wo = self._hin()
        ohne_doppelte = [w for i, w in enumerate(wo) if i == 0 or wo[i - 1] != w]
        self.assertEqual(ohne_doppelte, ["boden", "seite", "oben"], wo)
        self.assertGreaterEqual(wo.count("seite"), 2, "Aufbau: mehrere Schritte an der Stirnseite")
        # Anfangs erreicht der Kegel die Buehne gar nicht: eine Scheibe am Boden.
        self.assertIsNone(reihe[0]["innen"])
        self.assertIsNone(reihe[0]["zwei"])
        self.assertAlmostEqual(reihe[0]["eins"][1], 0.01, places=6)

    def test_teil_auf_der_buehne_bleibt_an_der_stirnseite(self):
        """★ Review: ohne die Stirnseite gab es an/aus/an — der Teil auf der
        Buehne erschien, verschwand an der Stirnseite und kam wieder."""
        reihe, wo = self._hin()
        ab = next(i for i, z in enumerate(reihe) if z["innen"] is not None)
        for z, w in list(zip(reihe, wo))[ab:]:
            with self.subTest(tilt=z["tilt"], mitte=w):
                self.assertTrue(_auf_der_buehne(z), f"Teil auf der Buehne verschwunden: {z}")
                self.assertTrue(z["einsGeschnitten"])
                self.assertIsNotNone(z["zwei"])
                self.assertAlmostEqual(z["zwei"][1], 0.01, places=6,
                                       msg="der Rest liegt am Boden vor der Buehne")
                self.assertTrue(z["kegelGeschnitten"])
        innen = [z["innen"] for z, w in zip(reihe, wo) if w != "oben" and z["innen"] is not None]
        self.assertLess(innen[0], 0.1, "der Teil auf der Buehne beginnt klein")
        self.assertTrue(all(b >= a - 1e-9 for a, b in zip(innen, innen[1:])), innen)
        self.assertGreater(innen[-1], 0.9)

    def test_kein_sprung_von_boden_ueber_stirnseite_zur_oberseite(self):
        reihe, _wo = self._hin()
        _stetig(self, reihe)
        laenge = [z["laenge"] for z in reihe]
        rel = [abs(b - a) / a for a, b in zip(laenge, laenge[1:])]
        self.assertLess(max(rel), 0.06, f"Kegellaenge springt: {list(zip(self.TILTS, laenge))}")


class Viz107MehrereFlaechenTest(_KanteBasis):
    TIER = "low"

    def test_kleiner_hoeherer_koerper_nimmt_der_buehne_das_muster_nicht(self):
        """Review: gewaehlt wurde die HOECHSTE Oberseite, sobald der Kegel sie
        beruehrte — ein Wuerfel an der Buehnenkante nahm der Buehne ihren Teil
        weg. Jetzt zaehlt, wo mehr Muster falsch laege (Anteil mal Hoehe)."""
        self._start()
        self._flaeche("wuerfel", "platform", (2.2, 0.75, 1.5), (1.0, 1.5, 1.0))
        reihe = self._fahrt(self.TILTS, gobo_wheel=_RING)
        neben = [z for z in reihe if z["innen"] is not None]
        self.assertGreaterEqual(len(neben), 10)
        for z in neben:
            with self.subTest(tilt=z["tilt"]):
                self.assertEqual(z["neben"], "podest")
                self.assertAlmostEqual(z["eins"][1], _OBEN + 0.01, places=6)
        _stetig(self, reihe)

    def test_gobo_aus_raeumt_die_anordnung_ab(self):
        """Mitten im Zustand „Mitte neben der Buehne“ geht das Gobo aus: keine
        zweite Scheibe, kein Beschnitt bleibt haengen."""
        self._start()
        self._fahrt(self.TILTS[:25], gobo_wheel=_RING)
        mit = self._lage()
        self.assertIsNotNone(mit["innen"], "Aufbau: Mitte neben der Buehne, Kegel noch darauf")
        ohne = self._fahrt([self.TILTS[24]], gobo_wheel=0)[0]
        self.assertIsNone(ohne["innen"])
        self.assertIsNone(ohne["zwei"])
        self.assertFalse(ohne["einsGeschnitten"])
        self.assertFalse(ohne["kegelGeschnitten"])
        self.assertAlmostEqual(ohne["eins"][1], 0.01, places=6)
        wieder = self._fahrt([self.TILTS[24]], gobo_wheel=_RING)[0]
        self.assertTrue(_auf_der_buehne(wieder))
        self.assertAlmostEqual(wieder["innen"], mit["innen"], places=6)


class Viz107EckeTest(_KanteBasis):
    """Review: der Anteil auf der Buehne wurde nur in acht Richtungen des
    Fussabdrucks geprueft. Ein Geraet 1,5 m NEBEN der Seitenkante faehrt an
    der Ecke vorbei nach vorn: solange es neben der Buehne ist, trifft die
    Querrichtung die Platte — hinter der Ecke fiel sie in einem Schritt weg
    (Anteil 0,4 -> 0), und mit ihr der Teil des Musters auf der Buehne."""
    TIER = "low"
    GERAETE = [_geraet(tiltRange=270, x=4.5)]
    TILTS = list(range(128, 86, -1))

    def test_an_der_ecke_vorbei_ohne_sprung(self):
        self._start()
        reihe = self._fahrt(self.TILTS, gobo_wheel=_RING)
        self.assertFalse(any(z["mitteOben"] or z["mitteSeite"] for z in reihe),
                         "Aufbau: die Strahlmitte bleibt am Boden neben der Buehne")
        innen = [z["innen"] or 0.0 for z in reihe]
        folge = [round(i, 3) for i in innen]
        self.assertGreater(innen[0], 0.25, f"Aufbau: neben der Buehne trifft der Kegel sie: {folge}")
        self.assertLess(innen[-1], 0.01, f"Aufbau: am Ende hat der Kegel die Buehne verlassen: {folge}")
        schritte = [abs(b - a) for a, b in zip(innen, innen[1:])]
        self.assertLess(max(schritte), 0.12, f"Anteil auf der Buehne springt: {folge}")
        _stetig(self, reihe)
