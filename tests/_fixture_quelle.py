"""Frisch aus `fixture_db.py` geseedete Library fuer Profil-Tests.

**Warum es diesen Helfer gibt.** Die Fixture-Profile stehen im Quelltext und
werden EINMAL in eine Datei geschrieben (``~/.local/share/LightOS/fixtures.db``).
``ensure_builtins()`` legt ein Builtin nur an, wenn sein ``short_name`` **fehlt**
— steht es schon drin, wird der Quelltext nie wieder angesehen. Ein Test, der
diese Datei liest, prueft damit **den Stand vom ersten Lauf**, nicht die Quelle,
die man gerade aendert. In der CI faellt das nicht auf, weil die DB dort leer
startet; auf jedem Entwicklerrechner ist der Test blind.

Genau das ist am 2026-08-02 passiert: ``test_claypaky_mythos_profile.py`` blieb
bei der Mutation „Zoomkanal ``zoom`` → ``raw``" **12/12 gruen**. Die uebrigen
Profil-Tests sahen sie, weil sie sich die Konstruktion jeweils selbst
hinkopiert hatten — 17 Kopien, bereits in zwei Varianten auseinandergelaufen.
Der Test, der sie NICHT kopierte, war der blinde. Deshalb liegt sie jetzt hier.

**Und sie raeumt auf.** Die kopierte Fassung benutzte ``tempfile.mktemp()`` und
loeschte nichts: gemessen **4 zurueckgelassene Datenbanken pro Lauf** allein aus
``test_spider_profile.py``, auf diesem Rechner **1935 Dateien / 218 MB** an einem
einzigen Tag.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from sqlalchemy.orm import Session


def frische_library(fall):
    """Engine auf einer frisch geseedeten Library — aus dem QUELLTEXT gebaut.

    ``fall`` ist der Testfall: die Klasse (Aufruf aus ``setUpClass``) oder die
    Instanz (Aufruf aus ``setUp``). Das Aufraeumen wird dort registriert, es
    braucht also kein ``tearDownClass``.

    Setzt zusaetzlich ``fixture_db._engine`` um, damit auch Code, der sich die
    Engine selbst holt, waehrend des Tests die frische Library sieht — und
    stellt den alten Zustand danach wieder her.
    """
    from src.core.database import fixture_db as FDB
    from src.core.database.fixture_db import _seed, get_engine

    verzeichnis = tempfile.mkdtemp(prefix="lightos_fixtures_")
    alt = FDB._engine
    motor = get_engine(os.path.join(verzeichnis, "fixtures.db"))
    with Session(motor) as s:
        _seed(s)
        s.commit()
    FDB._engine = motor

    def zurueck():
        FDB._engine = alt
        try:
            motor.dispose()
        except Exception:
            pass
        shutil.rmtree(verzeichnis, ignore_errors=True)

    aufraeumen = (fall.addClassCleanup if isinstance(fall, type)
                  else fall.addCleanup)
    aufraeumen(zurueck)
    return motor
