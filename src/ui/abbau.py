"""STAB-42: Qt-Ereignisse waehrend des Abbaus eines Widgets still uebergehen.

Raeumt Pythons Speicherbereinigung ein Widget ab (Widget im Referenzzyklus,
z. B. ``self._ich = self`` oder eine Signalverbindung auf eine eigene
Methode), leert sie zuerst das Instanz-Woerterbuch und loest erst danach das
C++-Objekt auf. Qt schickt beim Zerstoeren aber noch Ereignisse an die
Python-Overrides (belegt: ``hideEvent`` eines Kind-Widgets, dessen Eltern
eingesammelt werden). Greift das Override dann auf ``self.<attribut>`` zu,
entsteht ``AttributeError`` — und die Ausnahme landet in dem Code, der
gerade laeuft, z. B. im ``paintEvent`` eines ANDEREN Widgets waehrend
``grab()``. Dessen Maler bleibt offen, danach stuerzt der Prozess beim
Aufraeumen nativ ab.

``abbau_still`` vor ein Ereignis-Override gesetzt prueft VOR dem Aufruf, ob
das Objekt im Abbau ist, und kehrt dann still zurueck — ohne das Override
und ohne ``super()``. Ausnahmen werden NICHT abgefangen: ein echter Fehler in
einem gesunden Objekt bleibt laut.

Kriterium (``im_abbau``):

* das Instanz-Woerterbuch ist leer — ein gesundes Widget dieses Programms
  setzt in ``__init__`` immer eigene Attribute, und die Probe zu STAB-42
  zeigt, dass im Abbau nicht einzelne Attribute fehlen, sondern das ganze
  Woerterbuch leer ist (``vars(self) == {}``, ``shiboken6.isValid`` noch
  ``True``); oder
* ``shiboken6.isValid(self)`` ist ``False`` (C++-Objekt schon weg).
"""
from __future__ import annotations

import functools

try:  # pragma: no cover - shiboken6 kommt mit PySide6
    from shiboken6 import isValid as _gueltig
except Exception:  # pragma: no cover
    def _gueltig(_obj) -> bool:
        return True

#: Wie oft ein Ereignis im Abbau uebergangen wurde (nur zur Diagnose/Tests).
uebergangen = 0


def im_abbau(obj) -> bool:
    """True, wenn ``obj`` gerade abgebaut wird (siehe Modulkopf)."""
    d = getattr(obj, "__dict__", None)
    if d is not None and not d:
        return True
    try:
        return not _gueltig(obj)
    except Exception:
        return False


def _schutz(rueckgabe):
    def dekorator(methode):
        @functools.wraps(methode)
        def huelle(self, *args, **kwargs):
            if im_abbau(self):
                global uebergangen
                uebergangen += 1
                return rueckgabe
            return methode(self, *args, **kwargs)
        huelle.__abbau_still__ = True
        return huelle
    return dekorator


#: Fuer Ereignis-Overrides (hideEvent, closeEvent, changeEvent, leaveEvent,
#: focusOutEvent …): im Abbau ``None`` zurueck, sonst unveraendert.
abbau_still = _schutz(None)

#: Fuer ``eventFilter``: im Abbau ``False`` (Ereignis nicht verbrauchen).
abbau_still_filter = _schutz(False)
