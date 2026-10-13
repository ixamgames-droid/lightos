"""OUT-76: Texte zur Treiber-Lage von uDMX-Adaptern unter Windows — ohne Qt.

Gebraucht vom Reiter „uDMX (USB)“ (``src/ui/udmx_treiber_hinweis.py``) und vom
Diagnosepaket (``diagnose_log.udmx_infos``). Die Schritte selbst stehen in
``udmx.windows_treiber_schritte``.
"""
from __future__ import annotations

from src.core.dmx import udmx


def befund_daten(befund) -> dict:
    """Ein ``UsbTreiber`` als einfache Daten (wandert aus dem Such-Thread)."""
    return {"kennung": befund.kennung, "lage": befund.lage,
            "dienst": befund.dienst, "problem": int(befund.problem or 0),
            "meldet": befund.name,
            "name": udmx.geraete_name(befund.vid, befund.pid),
            "sicher": udmx.treiber_befund_sicher(befund)}


def ohne_treiber(befunde) -> list[dict]:
    """Die angesteckten Adapter, die am Treiber scheitern."""
    return [b for b in (befunde or [])
            if b.get("lage") in (udmx.T_FEHLT, udmx.T_ANDERER)]


def befund_satz(b: dict) -> str:
    """Ein Satz je Adapter: was Windows ueber ihn sagt."""
    wer = f"{b.get('name') or 'uDMX-Adapter'} ({b.get('kennung')})"
    if b.get("meldet") and b.get("meldet") not in wer:
        wer += f", meldet sich als „{b['meldet']}“"
    if not b.get("sicher", True):
        wer = (f"Ein Gerät mit der geteilten Kennung {b.get('kennung')} "
               f"(vermutlich ein {b.get('name')})")
    if b.get("lage") == udmx.T_ANDERER:
        return (f"{wer} steckt am USB, aber Windows hat ihm den Treiber "
                f"„{b.get('dienst')}“ zugeordnet — damit kann LightOS ihn "
                f"nicht ansprechen.")
    grund = (" (Geräte-Manager: „Treiber nicht installiert“)"
             if b.get("problem") == 28 else "")
    return (f"{wer} steckt am USB, aber Windows hat ihm keinen Treiber "
            f"zugeordnet{grund}.")


def diagnose_zeilen(befunde) -> list[str]:
    """Zeilen fuer das Diagnosepaket: je angestecktem Adapter die Treiber-Lage,
    und wenn einer scheitert, die Schritte als Text."""
    zeilen = []
    for b in befunde or []:
        if b.get("lage") == udmx.T_PASST:
            zeilen.append(f"Windows-Treiber {b.get('name')} ({b.get('kennung')}): "
                          f"{b.get('dienst')} — passt")
        else:
            zeilen.append("Windows-Treiber: " + befund_satz(b))
    if ohne_treiber(befunde):
        zeilen.append("So wird der Treiber zugewiesen (LightOS installiert keinen):")
        erster = ohne_treiber(befunde)[0]
        for i, s in enumerate(udmx.windows_treiber_schritte(erster.get("kennung") or ""), 1):
            zeilen.append(f"  {i}. {s}")
        zeilen.append("  " + udmx.windows_treiber_achtung())
    return zeilen
