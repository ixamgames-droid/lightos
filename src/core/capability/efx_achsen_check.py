"""LAS-23 — Show-Lint: zeigt ein EFX auf Geraete, die seine Achsen nicht haben?

Ein Bewegungs-EFX schreibt pro Ziel genau zwei Attribute: ``pan_attr`` und
``tilt_attr`` (Standard ``pan``/``tilt``, fuer Laser z. B. ``laser_x``/
``laser_y``). Hat das gepatchte Geraet KEINES der beiden, schreibt der Effekt
still nichts — genau so lief ein Laser-EFX nach dem Laden, solange die Show-Datei
die Achsen nicht mitspeicherte.

★ Nur eine WARNUNG und nur, wenn BEIDE Achsen fehlen: ein Spider ohne Pan (nur
Tilt-Koepfe) ist ein gewolltes Ziel. Profil unbekannt -> kein Befund (schweigen
statt raten, wie ``dimmer_check``).
"""
from __future__ import annotations

from .validate import Finding, WARNING


def _zahl(x, standard=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return standard


def _funktionen(show: dict) -> list[dict]:
    block = show.get("functions")
    if isinstance(block, dict):
        block = block.get("functions", []) or []
    if not isinstance(block, list):
        return []
    out = [f for f in block if isinstance(f, dict)]
    # Alt-Shows: EFX im separaten Block (wird beim Laden migriert).
    alt = show.get("efx")
    if isinstance(alt, list):
        out += [dict(f, type="EFX", motion=True) for f in alt if isinstance(f, dict)]
    return out


def _ist_bewegungs_efx(fd: dict) -> bool:
    return fd.get("type") == "EFX" and bool(fd.get("motion") or "speed_hz" in fd)


def efx_achsen_befunde(show: dict) -> list[Finding]:
    """Warnungen fuer EFX-Ziele, deren Geraet weder ``pan_attr`` noch
    ``tilt_attr`` als Kanal-Attribut besitzt."""
    patch = show.get("patch")
    if not isinstance(patch, list):
        return []
    patch_by_fid: dict[int, dict] = {}
    for pf in patch:
        if isinstance(pf, dict):
            patch_by_fid.setdefault(_zahl(pf.get("fid"), -1), pf)
    try:
        from types import SimpleNamespace
        from src.core.app_state import get_channels_for_patched
    except Exception:
        return []
    attr_cache: dict[int, set[str] | None] = {}

    def _attrs(fid: int) -> set[str] | None:
        if fid in attr_cache:
            return attr_cache[fid]
        pf = patch_by_fid.get(fid)
        res: set[str] | None = None
        if pf is not None:
            fake = SimpleNamespace(
                fixture_profile_id=_zahl(pf.get("fixture_profile_id"), 0),
                mode_name=str(pf.get("mode_name") or ""),
                channel_count=_zahl(pf.get("channel_count"), 1),
                address=_zahl(pf.get("address"), 1),
                spider_dual_tilt=bool(pf.get("spider_dual_tilt", False)))
            try:
                chans = list(get_channels_for_patched(fake) or ())
            except Exception:
                chans = []
            if chans:
                res = {(getattr(c, "attribute", "") or "").lower() for c in chans}
        attr_cache[fid] = res
        return res

    befunde: list[Finding] = []
    for i, fd in enumerate(_funktionen(show)):
        if not _ist_bewegungs_efx(fd):
            continue
        for t in (fd.get("fixtures") or []):
            if not isinstance(t, dict):
                continue
            fid = _zahl(t.get("fid"), -1)
            pa = str(t.get("pan_attr") or "pan")
            ta = str(t.get("tilt_attr") or "tilt")
            attrs = _attrs(fid)
            if attrs is None:          # nicht gepatcht oder Profil unbekannt
                continue
            if pa.lower() in attrs or ta.lower() in attrs:
                continue
            pf = patch_by_fid.get(fid) or {}
            label = str(pf.get("label") or f"fid {fid}")
            befunde.append(Finding(
                WARNING, "EFX-ACHSE-FEHLT",
                f"EFX '{fd.get('name', '?')}' -> '{label}'",
                f"bewegt '{pa}'/'{ta}', das Geraet hat keinen dieser Kanaele — "
                f"der Effekt schreibt dort nichts. Laser brauchen "
                f"pan_attr='laser_x', tilt_attr='laser_y'.",
                "efx.py EfxFixture.pan_attr/tilt_attr (LAS-23)"))
    return befunde
