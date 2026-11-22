"""WEB-17: Titel einer Handy-Gruppe wird nicht abgeschnitten.

Liegen die Kacheln einer Gruppe nicht nebeneinander, bekommt jede Kachel einen
eigenen Rahmen und nur die erste den Titel. Unter einer schmalen Kachel stand
dann „Handy-T…“ statt „Handy-Test (nur Handy)“. Der Titel bricht jetzt innerhalb
seines Rahmens um, statt mit Auslassungszeichen abgeschnitten zu werden, und
wächst nur in die eigene Kachel hinein (nicht über fremde Kacheln).
Gleiches gilt für den Titel eines Solo-Rahmens („… (immer nur eine)“).
"""

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KONSOLE = os.path.join(_REPO, "src", "web", "templates", "konsole.html")


def _html():
    with open(_KONSOLE, encoding="utf-8") as fh:
        return fh.read()


def _css():
    html = _html()
    a = html.index("<style")
    b = html.index("</style>", a)
    # Kommentare entfernen, damit nur echte Regeln zählen
    return re.sub(r"/\*.*?\*/", "", html[a:b], flags=re.S)


def _regeln(css):
    """Liste (Selektor, {Eigenschaft: Wert}) aller einfachen Regeln."""
    raus = []
    for sel, rumpf in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        werte = {}
        for teil in rumpf.split(";"):
            if ":" in teil:
                k, v = teil.split(":", 1)
                werte[k.strip()] = v.strip()
        for s in sel.split(","):
            raus.append((" ".join(s.split()), werte))
    return raus


def _titel_regeln():
    return [(s, w) for s, w in _regeln(_css())
            if s.startswith(".gruppe") and s.endswith(".titel")]


class GruppenTitelTest(unittest.TestCase):

    def test_grundregel_bricht_um_statt_abzuschneiden(self):
        grund = dict(_titel_regeln())[".gruppe .titel"]
        self.assertEqual(grund.get("white-space"), "normal")
        self.assertNotIn("text-overflow", grund)
        self.assertNotEqual(grund.get("overflow"), "hidden")
        # auch ein langes Wort ohne Leerzeichen passt in die Kachel
        self.assertEqual(grund.get("overflow-wrap"), "anywhere")

    def test_keine_titel_regel_schneidet_ab(self):
        # weder Handy- noch Solo-Rahmen noch Einzel-Kachel holen das Abschneiden zurück
        regeln = _titel_regeln()
        self.assertGreaterEqual(len(regeln), 3)
        for sel, w in regeln:
            with self.subTest(selektor=sel):
                self.assertNotEqual(w.get("white-space"), "nowrap")
                self.assertNotIn("ellipsis", w.get("text-overflow", ""))
                self.assertNotEqual(w.get("overflow"), "hidden")

    def test_titel_bleibt_in_der_breite_des_eigenen_rahmens(self):
        # nicht über die Kachel hinaus -> keine fremde Kachel daneben überdeckt
        grund = dict(_titel_regeln())[".gruppe .titel"]
        self.assertEqual(grund.get("position"), "absolute")
        m = re.fullmatch(r"calc\(100% - (\d+)px\)", grund.get("max-width", ""))
        self.assertIsNotNone(m, grund.get("max-width"))
        links = int(grund["left"].rstrip("px"))
        self.assertGreaterEqual(links, 0)
        self.assertLessEqual(links, int(m.group(1)))
        self.assertEqual(grund.get("box-sizing"), "border-box")
        for sel, w in _titel_regeln():
            with self.subTest(selektor=sel):
                self.assertNotIn("width", w)
                if "max-width" in w:
                    self.assertTrue(w["max-width"].startswith("calc(100% -"), w["max-width"])

    def test_titel_waechst_in_die_eigene_kachel(self):
        regeln = dict(_titel_regeln())
        # Solo-Rahmen: oben angeschlagen -> mehr Zeilen wachsen nach unten in die Kachel
        self.assertEqual(regeln[".gruppe .titel"].get("top"), "-8px")
        # Handy-Gruppe: unten angeschlagen -> mehr Zeilen wachsen nach oben in die Kachel
        handy = regeln[".gruppe.handy .titel"]
        self.assertEqual(handy.get("bottom"), "-8px")
        self.assertEqual(handy.get("top"), "auto")

    def test_voller_titel_im_aufbau(self):
        html = _html()
        # Der Text wird ungekürzt gesetzt, nur an der ersten Einzel-Kachel.
        self.assertIn("t.textContent = '◉ ' + g.titel;", html)
        self.assertIn("titel: i === 0, einzeln: true", html)
        self.assertNotIn("g.titel.slice(", html)
        self.assertNotIn("g.titel.substr", html)


if __name__ == "__main__":
    unittest.main()
