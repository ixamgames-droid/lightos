"""Der Modus eines gepatchten Geraets — EINE Regel fuer alle, die danach fragen.

Ein gepatchtes Geraet merkt sich seinen Modus als ``(Profil, Modusname,
Kanalzahl)``, nicht als Modus-ID. Wer daraus wieder den ``FixtureMode`` macht,
muss ueberall dasselbe meinen: die Kanaele im Renderpfad, die Rasterform im
3D-Fenster, die Show-Pruefung beim Oeffnen und die Dialoge im Patch.

Die Regel (``modus_waehlen``):

  1. exakter Name — tragen mehrere Modi den Namen, der mit passender
     Kanalzahl (FM-67), sonst der erste nach ID,
  2. irgendein Modus mit passender Kanalzahl (der erste nach ID),
  3. der erste Modus des Profils,
  4. ``None``.

FM-73: bis dahin stand die Regel in ``app_state._resolve_mode`` und — leicht
anders, mit ``scalar_one_or_none()`` — noch einmal in ``sync.validate_and_
repair``. Die zweite Fassung warf bei gleichnamigen Modi und bei zwei Modi
gleicher Kanalzahl ``MultipleResultsFound``. Deshalb liegt die Regel jetzt
hier, ohne Qt und ohne ``app_state``, und beide fragen sie.

Bewusst ueber eine fertige LISTE von Modi und nicht ueber Abfragen: so gilt
dieselbe Funktion fuer eine Session (``modi_des_profils``) wie fuer die
abgehaengten Objekte aus ``fixture_db.get_modes`` (Dialoge).
"""
from __future__ import annotations

#: Breite der Spalte ``fixture_modes.name``.
MODUSNAME_MAX = 80


def modi_des_profils(session, profil_id) -> list:
    """Alle Modi eines Profils, nach ID. ``profil_id`` ``None`` -> ``[]``."""
    if profil_id is None:
        return []
    from sqlalchemy import select
    from .models import FixtureMode
    return list(session.execute(
        select(FixtureMode)
        .where(FixtureMode.fixture_id == profil_id)
        .order_by(FixtureMode.id)
    ).scalars().all())


def _nach_id(modi) -> list:
    return sorted(modi, key=lambda m: getattr(m, "id", None) or 0)


def gleichnamiger_modus(modi, name, kanalzahl):
    """Stufe 1 allein: der Modus mit genau diesem Namen, oder ``None``.

    Das ist zugleich die Antwort auf „gibt es den gespeicherten Modus noch?“
    (Show-Pruefung). Unter mehreren gleichnamigen gewinnt der mit passender
    Kanalzahl, sonst der erste nach ID."""
    gleichnamig = [m for m in _nach_id(modi) if m.name == name]
    return next((m for m in gleichnamig if m.channel_count == kanalzahl),
                gleichnamig[0] if gleichnamig else None)


def modus_waehlen(modi, name, kanalzahl):
    """Die ganze Kette (Stufen 1-4, s. Modulkopf) ueber eine Liste von Modi."""
    sortiert = _nach_id(modi)
    return (gleichnamiger_modus(sortiert, name, kanalzahl)
            or next((m for m in sortiert if m.channel_count == kanalzahl), None)
            or (sortiert[0] if sortiert else None))


def doppelte_modusnamen(namen) -> list[str]:
    """Die Namen, die in ``namen`` mehr als einmal vorkommen (sortiert)."""
    namen = list(namen)
    return sorted({n for n in namen if namen.count(n) > 1})


def eindeutiger_modusname(name: str, vergeben: set) -> str:
    """``name``, notfalls mit Suffix „ (n)“, so dass er in ``vergeben`` noch
    nicht vorkommt — und traegt ihn dort ein.

    Fuer die Wege, auf denen niemand gefragt werden kann (Datei-Import,
    fertiges Payload). Dasselbe Suffix wie beim Bibliotheksformat
    (``bibliothek_format.fuer_format_anpassen``). Das Ergebnis passt in die
    Spalte (``MODUSNAME_MAX``)."""
    neu = name
    n = 2
    while neu in vergeben:
        anhang = f" ({n})"
        neu = name[:MODUSNAME_MAX - len(anhang)].rstrip() + anhang
        n += 1
    vergeben.add(neu)
    return neu
