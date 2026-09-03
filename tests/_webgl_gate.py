"""QA-74: EINE Quelle fuer die Frage „die Szene kam nicht hoch — was nun?".

Drei Szenen-Testdateien rufen ``view.show()`` und koennen deshalb den
GL-Kontext-Ausfall sehen, den XPLAT-17 gemessen hat: Chromium verliert beim
Start den Kontext IM EIGENEN Prozess (``Context lost during MakeCurrent`` →
``Error creating WebGL context``), three.js kommt gar nicht erst hoch, und
``__lightosAppReady`` bleibt aus.

★ **Warum es diese Datei gibt.** Dieselbe Frage wurde an drei Stellen drei Mal
verschieden beantwortet:

* ``test_viz14_place_ghost_scene.py`` (QA-70) — Diagnose lesen, bei GL-Ausfall
  **ueberspringen**.
* ``test_viz14_drag_scene.py`` (XPLAT-17/19) — **einmal neu laden**, wie es das
  Produkt selbst tut (VIZ-SCENE-SELFHEAL laedt nach genau einem verlorenen
  Kontext neu), danach scheitern.
* ``test_viz14_deselect_scene.py`` (XPLAT-19) — sofort scheitern, nur mit
  Diagnose.

Gefunden hat es Sitzung A im Gate-Lauf zu FM-41: ``drag`` fiel mit 3 von 3
Methoden und trug Zeichen fuer Zeichen die QA-70-Signatur — isoliert lief es in
6,5 s durch, und es lief keine LightOS-Instanz (XPLAT-14 scheidet aus). Der
Neuversuch dort hat also nicht gereicht: auch der zweite Anlauf bekam keinen
Kontext, und dann scheitert der Test an einer Zusicherung, die er **gar nicht
pruefen konnte**.

**Die gemeinsame Antwort nimmt beide guten Haelften in der richtigen
Reihenfolge:**

1. Diagnose lesen, **bevor** neu geladen wird (XPLAT-19: danach sind die Flags
   der gescheiterten Ladung weg).
2. Ist es ein GL-Kontext-Ausfall und war es der erste Anlauf → **laut warnen und
   einmal neu laden**. Das wiederholt nur den Seiten-Aufbau, nicht den Test.
3. Ist es ein GL-Kontext-Ausfall und der Neuversuch lief schon → **ueberspringen**
   mit benanntem Grund. Ein Test, der an einer ungeprueften Zusicherung
   scheitert, faerbt jeden fremden Branch rot und verstellt die Frage „liegt es
   an meinem Diff?".
4. Alles andere → **scheitern**, mit Diagnose.

⚠️ **Die Erkennung ist bewusst ENG.** Die Gefahr liegt nicht im Flake, sondern in
der Reparatur: ein Ueberspringer, der zu viel schluckt, versteckt echte
Szenenfehler hinter einem gruenen Lauf. Geprueft wird ausschliesslich das
``err``-Feld der Diagnose gegen die gemessenen Wortlaute; ein ``TypeError``, ein
``ReferenceError``, eine leere Ursache und eine unlesbare Diagnose bleiben
Testfehler (QA-53: im Zweifel rot).
"""
from __future__ import annotations

import json
import unittest
import warnings

#: Wortlaute aus dem Segment-Log (QA-70, 2026-09-01; QA-74, 2026-09-03).
GL_AUSFALL_MERKMALE = ("webgl", "makecurrent", "context lost", "webgl context")

#: Die sieben Felder, die den Abbruch verorten (XPLAT-19). Bewusst OHNE
#: ``getContext`` — das waere genau die Ressource, die hier unter Verdacht steht.
DIAGNOSE_JS = ("JSON.stringify({"
               "err: String(window.__lightosSceneError || ''),"
               "ready: !!window.__lightosAppReady,"
               "three: typeof window.THREE,"
               "api: typeof window.__lightos,"
               "chan: !!(window.qt && window.qt.webChannelTransport),"
               "canvas: document.getElementsByTagName('canvas').length,"
               "doc: document.readyState})")


def ist_gl_kontext_ausfall(diagnose) -> bool:
    """Beschreibt ``diagnose`` einen verlorenen/nicht erzeugbaren GL-Kontext?

    ``diagnose`` ist die JSON-Zeile aus der Szenen-Diagnose. Geprueft wird
    ausschliesslich das ``err``-Feld: die uebrigen Felder (``canvas: 0``,
    ``api: undefined``) treten bei einem GL-Ausfall zwar ebenfalls auf, aber
    genauso bei einem echten Skriptfehler — sie taugen nicht zur Unterscheidung.
    """
    if not diagnose:
        return False
    try:
        felder = json.loads(diagnose)
    except (ValueError, TypeError):
        return False
    if not isinstance(felder, dict):
        return False
    fehler = str(felder.get("err") or "").lower()
    return any(merkmal in fehler for merkmal in GL_AUSFALL_MERKMALE)


def nach_szenen_timeout(fehler, diagnose, *, zweiter_versuch: bool) -> bool:
    """Die EINE Entscheidung. ``True`` heisst: einmal neu laden.

    Sonst wirft sie — ``unittest.SkipTest`` beim wiederholten GL-Ausfall,
    ``AssertionError`` (mit Diagnose) in jedem anderen Fall. Der Aufrufer
    braucht damit nur zwei Zeilen und keine eigene Meinung.
    """
    if ist_gl_kontext_ausfall(diagnose):
        if not zweiter_versuch:
            # ★ Kein „retry" im verbotenen Sinn: wiederholt wird der
            # Seiten-Aufbau, nicht der Test — und genau einmal, wie im Produkt.
            # Laut, damit aus „heilt sich" nie „faellt niemandem auf" wird:
            # der Runner laeuft ohne -s, ein print waere unsichtbar.
            warnings.warn(
                "XPLAT-17/19: Szene kam nicht hoch (GL-Kontext), EIN "
                f"Neuversuch wie VIZ-SCENE-SELFHEAL. Diagnose: {diagnose}",
                RuntimeWarning, stacklevel=3)
            return True
        raise unittest.SkipTest(
            "Kein WebGL-Kontext — QtWebEngine konnte auch im zweiten Anlauf "
            "keinen erzeugen bzw. hat ihn verloren. Die Szene ist damit nicht "
            "pruefbar; das ist KEIN Fehler im Szenen-Code. "
            f"Szenen-Diagnose: {diagnose} (QA-70/QA-74)")
    raise AssertionError(f"{fehler} | Szenen-Diagnose: {diagnose}") from None


def szenen_diagnose(view, pump, timeout_s: float = 2.0) -> str:
    """Die sieben Felder aus der laufenden Seite lesen.

    Bewusst NICHT ueber den ``_eval``-Helfer der Testdateien: der assertet bei
    Zeitueberschreitung und wuerde die eigentliche Fehlermeldung durch seine
    eigene ersetzen.
    """
    import time
    box: list = []
    try:
        view.page().runJavaScript(DIAGNOSE_JS, box.append)
        ende = time.monotonic() + timeout_s
        while not box and time.monotonic() < ende:
            pump(0.05)
    except Exception as e:                      # Page/View schon tot
        return f"nicht lesbar: {e!r}"
    return box[0] if box else "kein Rueckruf (Renderer-Prozess tot?)"
