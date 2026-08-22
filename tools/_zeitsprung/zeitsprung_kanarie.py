"""pytest-Plugin: belegt IM Testprozess, dass der Zeitsprung wirklich wirkt.

★ Warum es das gibt. Der Zeitbomben-Waechter (``tools/zeitbomben_gate.py``)
faehrt verdaechtige Testdateien mit vorgerueckter Uhr. Faellt der Uhr-Vorspann
still aus — ``PYTHONPATH`` verlorengegangen, Umgebungsvariable nicht
durchgereicht, ``sitecustomize`` von einem anderen Paket verdeckt —, dann laeuft
alles mit der ECHTEN Uhr, alles ist gruen, und der Waechter meldet „keine
Zeitbomben". Ein Gate, das genau dann Ruhe meldet, wenn es blind ist, ist
schlimmer als keines.

Deshalb prueft dieses Plugin die Uhr **in demselben Prozess, in dem die
Kandidaten laufen** (nicht in einem Nachbarprozess mit derselben Umgebung), und
schreibt eine Zeile auf stderr, die der Waechter positiv verlangt::

    ZEITSPRUNG-WIRKSAM <datum> <staerke>

Fehlt die Zeile, bricht der Waechter mit einem Fehler ab statt „gruen" zu sagen.
Stimmt die Uhr nicht, bricht das Plugin die Sitzung sofort ab
(``ZEITSPRUNG-UNWIRKSAM``) — noch bevor ein Test laufen und faelschlich gruen
sein kann.

Geprueft wird jede Quelle, die die gewaehlte Staerke anfasst: in ``datum``
``date.today()`` und ``datetime.now()``, in ``alle`` zusaetzlich ``time.time()``.
Eine halb wirksame Verschiebung ist genauso gefaehrlich wie gar keine — und
``date.today()`` ueber ``datetime.now()`` zu decken reicht nicht: die beiden
haengen in CPython an verschiedenen Quellen (s. ``sitecustomize.py``).
"""
import datetime
import os
import sys
import time

import pytest

MARKE_OK = "ZEITSPRUNG-WIRKSAM"
MARKE_FEHLT = "ZEITSPRUNG-UNWIRKSAM"
ERWARTET_VAR = "LIGHTOS_ZEITSPRUNG_ERWARTET"
STAERKE_VAR = "LIGHTOS_ZEITSPRUNG_UHR"


def _quellen(staerke: str) -> dict:
    quellen = {
        "date.today()": datetime.date.today(),
        "datetime.now()": datetime.datetime.now().date(),
    }
    if staerke == "alle":
        quellen["time.time()"] = datetime.date.fromtimestamp(time.time())
    return quellen


def pytest_configure(config):
    roh = os.environ.get(ERWARTET_VAR, "").strip()
    if not roh:
        raise pytest.UsageError(
            f"{MARKE_FEHLT}: {ERWARTET_VAR} ist nicht gesetzt — das Plugin "
            "kann nicht pruefen, welchen Tag es sehen muesste.")
    erwartet = datetime.date.fromisoformat(roh)
    staerke = os.environ.get(STAERKE_VAR, "datum").strip() or "datum"

    # ± 1 Tag Spielraum: der Elternprozess rechnet den Sollwert kurz vorher aus,
    # ein Mitternachtswechsel dazwischen darf das Gate nicht rot machen.
    schief = {name: str(wert) for name, wert in _quellen(staerke).items()
              if abs((wert - erwartet).days) > 1}
    if schief:
        raise pytest.UsageError(
            f"{MARKE_FEHLT}: erwartet {erwartet}, aber {schief} — der "
            "Uhr-Vorspann (tools/_zeitsprung/sitecustomize.py) ist in diesem "
            "Prozess nicht (vollstaendig) wirksam. Ein Lauf ohne wirksamen "
            "Sprung beweist NICHTS.")

    print(f"{MARKE_OK} {erwartet} {staerke}", file=sys.stderr)
    sys.stderr.flush()
