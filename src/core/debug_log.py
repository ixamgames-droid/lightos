"""T-7: spam-sicheres Logging fuer ansonsten verschluckte Fehler.

Viele ``except Exception: pass`` im Code sind bewusst still (Best-Effort-Cleanup,
optionale Features, heisser Render-Pfad). Sie ganz zu entfernen wuerde Abstuerze
riskieren; sie hart zu loggen wuerde im 44-Hz-Pfad spammen. ``debug_swallow``
loest beides:

* **Default aus** — nur aktiv, wenn die Umgebungsvariable ``LIGHTOS_DEBUG``
  gesetzt ist (oder ``set_debug(True)``). In der normalen Auslieferung aendert
  sich nichts.
* **Dedupliziert** — jede einzigartige ``(tag, Fehlertyp, Meldung)``-Kombination
  wird genau einmal ausgegeben. Selbst ein Fehler, der jeden Frame feuert, loggt
  also nur ein Mal → kein Spam.

So bleibt das Verhalten in Produktion unveraendert, aber bei der Fehlersuche
(``LIGHTOS_DEBUG=1``) werden bisher unsichtbare Fehler nachvollziehbar.
"""
from __future__ import annotations
import os

_TRUE = {"1", "true", "yes", "on"}
_enabled = os.environ.get("LIGHTOS_DEBUG", "").strip().lower() in _TRUE
_seen: set[tuple[str, str, str]] = set()


def is_enabled() -> bool:
    return _enabled


def set_debug(on: bool) -> None:
    """Debug-Logging zur Laufzeit ein-/ausschalten (z. B. aus den Tests)."""
    global _enabled
    _enabled = bool(on)


def reset() -> None:
    """Den Dedup-Speicher leeren (v. a. fuer Tests)."""
    _seen.clear()


def debug_swallow(tag: str, exc: BaseException) -> None:
    """Loggt einen sonst verschluckten Fehler — nur bei aktivem Debug und je
    einzigartiger ``(tag, Fehler)``-Kombination genau einmal."""
    if not _enabled:
        return
    key = (tag, type(exc).__name__, str(exc))
    if key in _seen:
        return
    _seen.add(key)
    print(f"[debug:{tag}] verschluckter Fehler: {type(exc).__name__}: {exc}")
