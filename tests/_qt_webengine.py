"""XPLAT-09 — deterministischer Abbau von ``QWebEngineView`` im Test.

**Warum es diesen Helfer gibt**

Elf Testdateien bauen einen echten ``QWebEngineView``, laden ``stage_scene.html``
und pruefen die Szene per JavaScript. Alle elf raeumten nach demselben Muster ab::

    def tearDown(self):
        self._view.deleteLater()
        _pump(0.2)                      # dreht nur app.processEvents()

Das raeumt **nicht** ab, und der Grund ist subtiler als „der naechste View
kollidiert mit dem alten" — diese naheliegende Erklaerung ist widerlegt: es
crasht auch dann, wenn nie ein zweiter View gebaut wird, und drei gleichzeitig
lebende Views sind umgekehrt voellig harmlos.

Der Ablauf ist ein **Dangling-Pointer auf ein am ``QWebChannel`` registriertes
QObject**:

1. ``QCoreApplication.processEvents()`` stellt ``DeferredDelete``-Events nicht zu —
   Qt haelt sie bis zu der Event-Loop-Ebene zurueck, auf der ``deleteLater()``
   gepostet wurde, und im Test laeuft gar keine Loop.
2. ``view.deleteLater()`` gibt in PySide6 aber bereits das Ownership an C++ ab.
   Der View wird also **nie** zerstoert — und mit ihm bleiben ``QWebEnginePage``,
   der daran geparentete ``QWebChannel`` und der laufende Renderer-Prozess am Leben.
3. Die Bridge dagegen ist ein Python-eigenes ``QObject`` **ohne Qt-Parent**. Sobald
   unittest die TestCase-Instanz freigibt, stirbt ihr C++-Objekt sofort.
4. Zurueck bleibt ein lebender Channel mit einem unter ``"bridge"`` registrierten,
   bereits freigegebenen Objekt — auf das der weiterlaufende Renderer per
   ``qwebchannel.js`` zugreift. Beim naechsten Pumpen: ``SIGSEGV``.

Nicht zugestelltes ``DeferredDelete`` ist damit der **Ermoeglicher** (es erzeugt das
Lebensdauer-Ungleichgewicht), nicht der Mechanismus. Belegt durch die Faktor-Reihe:
Bridge behalten = gruen · Bridge vorher abmelden = gruen · Transport kappen = gruen ·
gar keine Bridge = gruen · ``about:blank``, das die Bridge nie anfasst = gruen ·
View und Bridge gemeinsam sofort zerstoeren = gruen. Nur das Ungleichgewicht crasht.

Es ist entsprechend ein **Race**, kein deterministischer Konflikt: dieselbe Datei
stirbt mal im 2., mal im 3. Zyklus, und mit einer 5-Sekunden-Pumpe gar nicht mehr
(dann ist der WebChannel-Handshake durch). Laenger pumpen ist deshalb **keine**
Loesung — es kaschiert nur das Race und laesst die Views trotzdem lecken.

Getrennt davon steht ein **zweiter** Defekt: jeder ueberlebende View laesst den
Prozess am Interpreter-Ende mit ``Release of profile requested but WebEnginePage
still not deleted`` und Exitcode 139 sterben — auch nach einem gemeldeten
``N passed``. Deshalb genuegt es nicht, nur die Bridge abzumelden; der View muss
wirklich weg.

Gemessen auf dem Linux-Rig (PySide6 6.x, ``QT_QPA_PLATFORM=offscreen``): alle elf
Dateien endeten mit ``SIGSEGV``. Zwei mitten im Lauf (``test_viz_shadow_dispose``
im 2., ``test_viz13_scene_modules_smoke`` im 3. View-Zyklus), die uebrigen neun
erst beim Prozessende — also **nach** dem gemeldeten Ergebnis, weshalb sie als
„gruen" durchgingen. Dieser Unterschied ist reine Zyklenzahl, kein Strukturvorteil:
eine der gruenen Dateien um sechs triviale Tests erweitert stirbt ebenfalls im
dritten Zyklus, und eine der roten auf zwei Tests gekuerzt wird gruen.

Wie teuer die Umgehung war, steht in ``test_viz14_mode_frame_scene`` selbst
geschrieben: die Datei deckelte sich **bewusst auf zwei Testmethoden**, weil „>~3
sequentielle QWebEngine-Vollladungen in EINEM Prozess den offscreen-Chromium-
Renderer kippen". Der Bug hat also Testabdeckung gekostet, nicht nur Exitcodes.

**Was der Helfer macht**

``deleteLater()`` posten und die Zustellung dann auch wirklich erzwingen —
einmal sofort, einmal nach dem Pumpen (der Abbau postet selbst weitere
Delete-Events).

**Plattform**: reines Qt-Core-API, keine Chromium-/Linux-Spezifika, keine
Umgebungsvariablen, keine Plattformweiche. Auf Windows/WinARM stellt es nur zu,
was ``deleteLater()`` ohnehin gepostet hat — im schlechtesten Fall ein No-op.

**Abgrenzung — Produktionscode ist nicht betroffen und braucht den Helfer nicht.**
Geprueft, mit zwei unabhaengigen Gruenden:

* Das Lebensdauer-Ungleichgewicht kann dort gar nicht entstehen: Bridge **und**
  Channel bekommen einen Qt-Parent (``visualizer_view.py:160-161``,
  ``visualizer_window.py:2127-2128`` — jeweils ``self``). Sie haengen im
  Widget-Baum und sterben gemeinsam mit ihm, nie einzeln.
* Die App laeuft in ``app.exec()``, wo ``DeferredDelete`` normal zugestellt wird;
  in ``src/`` gibt es kein einziges ``processEvents()``. Views werden ausserdem
  immer sofort geparentet.

Nachgemessen am realen Popout-Zyklus (wiederholtes Ausklinken/Zurueckholen) sowie
am haertesten denkbaren Fall — neuer View im selben Callback direkt nach
``deleteLater()``: beides sauber.

Wer gar keinen echten Seitenladevorgang braucht, nimmt weiterhin die
View-freien Muster aus ``test_viz10_stability`` / ``test_viz12_service``
(``VisualizerWindow``-Subklasse mit uebersprungenem ``__init__``).
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent


def flush_deferred_deletes() -> None:
    """``DeferredDelete``-Events sofort zustellen.

    Genau die Zustellung, die ``processEvents()`` auslaesst.
    """
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def destroy_webengine_view(view, pump=None, pump_seconds: float = 0.2) -> None:
    """Einen ``QWebEngineView`` im Test deterministisch abbauen.

    Aufruf im ``tearDown``; die Test-Referenz danach auf ``None`` setzen::

        def tearDown(self):
            destroy_webengine_view(self._view, self._pump)
            self._view = None

    :param view: der abzubauende View (``None`` ist erlaubt und tut nichts).
    :param pump: die ``processEvents``-Pumpe des Tests, ``Callable(seconds)``.
        Ohne Angabe wird einmal direkt ``processEvents()`` gedreht.
    :param pump_seconds: Pumpdauer zwischen den beiden Zustellungen.
    """
    if view is not None:
        # Schritt 1 — den WebChannel-Transport kappen, bevor irgendetwas stirbt.
        # NICHT lasttragend: Schritt 2 allein ist gemessen ausreichend (auch dann,
        # wenn der Aufrufer die Bridge-Referenz VOR diesem Aufruf fallen laesst —
        # eigens geprueft). Das hier schliesst das Zeitfenster zusaetzlich an der
        # Ursache selbst, kostet einen Aufruf und macht den Helfer unabhaengig davon,
        # in welcher Reihenfolge ein kuenftiger Aufrufer seine Attribute aufraeumt.
        # Bewusst generisch ueber die Page, damit der Helfer die Attributnamen der
        # einzelnen Tests (``_bridge`` vs. ``_bridge_obj``) nicht kennen muss.
        try:
            view.page().setWebChannel(None)
        except Exception:
            pass

        # Schritt 2 — den View selbst abbauen.
        try:
            view.deleteLater()
        except Exception:
            # Der View kann bereits (per WA_DeleteOnClose o. ae.) weg sein —
            # das ist kein Testfehler, der Abbau ist dann schon passiert.
            pass

    # 1. Zustellung: loescht View und Page wirklich — und zwar SOLANGE die
    #    Python-Referenzen des Aufrufers (insbesondere die Bridge) noch leben.
    #    Genau darauf kommt es an: unittest gibt die TestCase-Instanz erst NACH
    #    tearDown frei, die Bridge ueberlebt den View hier also garantiert. Ohne
    #    diese Zustellung ist es umgekehrt — der View ueberlebt die Bridge, und
    #    das ist der Absturz.
    flush_deferred_deletes()

    if pump is not None:
        pump(pump_seconds)
    else:
        QCoreApplication.processEvents()

    # 2. Zustellung: der Abbau selbst postet weitere Delete-Events (Page,
    #    RenderWidgetHostView, WebChannel-Transport) — die muessen ebenfalls weg,
    #    bevor der naechste View gebaut wird.
    flush_deferred_deletes()
