"""STAB-DEDUP-OPT: verwaiste Patch-Zeilen anzeigen und (nur auf Ansage) in
Quarantäne verschieben.

    venv/bin/python tools/patch_quarantaene.py                  # nur anzeigen
    venv/bin/python tools/patch_quarantaene.py --anwenden       # verschieben
    venv/bin/python tools/patch_quarantaene.py --liste          # Quarantäne zeigen
    venv/bin/python tools/patch_quarantaene.py --zurueck 42     # zurückholen
    (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

**Ohne ``--anwenden`` wird nichts verändert.** Das ist keine Höflichkeit,
sondern die Absicherung: der Befund hängt an einem Scan über ein Dutzend
Referenz-Orte, und der Nutzer soll sehen, *warum* ein Gerät als Waise gilt,
bevor es sich bewegt.

Adress-Überlappungen werden mit ausgewiesen, sind aber **nie** ein Grund zur
Quarantäne — zwei Geräte auf derselben Adresse können beide gewollt sein.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show import patch_dedup                                # noqa: E402


def _zeile(b) -> str:
    ort = f"U{b.universe}:{b.address}"
    ueber = (f"  überlappt mit {b.ueberlappt_mit}" if b.ueberlappt_mit else "")
    if b.ist_kandidat:
        return f"  WAISE   #{b.fid:<4} {ort:<10} {b.label[:28]:<28}{ueber}"
    return (f"  benutzt #{b.fid:<4} {ort:<10} {b.label[:28]:<28}"
            f"  → {', '.join(b.fundstellen)}{ueber}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anwenden", action="store_true",
                    help="Kandidaten wirklich in die Quarantäne verschieben")
    ap.add_argument("--liste", action="store_true",
                    help="Inhalt der Quarantäne zeigen")
    ap.add_argument("--zurueck", type=int, metavar="FID",
                    help="ein Gerät aus der Quarantäne zurückholen")
    ap.add_argument("--alle", action="store_true",
                    help="auch die benutzten Geräte auflisten")
    ap.add_argument("--show", metavar="DATEI",
                    help="Show-Datei vorher laden (dort stehen Funktionen, "
                         "Cuelisten, VC-Layout und Snaps — NICHT in der DB)")
    ap.add_argument("--auch-ohne-show", action="store_true",
                    help="den Unbeladen-Riegel bewusst übergehen (nur, wenn die "
                         "Show wirklich keine Funktionen/Cues/VC/Snaps hat)")
    args = ap.parse_args()

    from src.core.app_state import get_state
    state = get_state()

    if args.show:
        from src.core.show.show_file import load_show
        load_show(state, args.show)
        print(f"Show geladen: {args.show}")

    if args.liste:
        eintraege = patch_dedup.liste_quarantaene(state)
        if not eintraege:
            print("Quarantäne ist leer.")
            return 0
        print(f"{len(eintraege)} Gerät(e) in Quarantäne:")
        for e in eintraege:
            print(f"  #{e['fid']:<4} U{e['universe']}:{e['address']:<4} "
                  f"{e['label'][:28]:<28} {e['verschoben_am']}  ({e['grund']})")
        return 0

    if args.zurueck is not None:
        ok = patch_dedup.zurueckholen(state, args.zurueck)
        print(f"#{args.zurueck} " + ("zurückgeholt." if ok else "nicht in Quarantäne."))
        return 0 if ok else 1

    if patch_dedup.wirkt_unbeladen(state) and not args.auch_ohne_show:
        print("ABBRUCH: der Patch ist gefüllt, aber es gibt weder Funktionen noch")
        print("Cuelisten, VC-Widgets oder Snaps. Das sieht nach einer NICHT")
        print("geladenen Show aus — dann läge jede Referenz außerhalb des Scans")
        print("und JEDES Gerät gälte als Waise.")
        print()
        print("  Show laden:            --show <datei.lshow>")
        print("  wirklich so gewollt:   --auch-ohne-show")
        return 2

    try:
        befunde = patch_dedup.analysiere(state)
    except patch_dedup.ScanUnvollstaendig as e:
        print(f"ABBRUCH: {e}")
        print("Es wird nichts verschoben — ein unvollständiger Scan könnte ein "
              "benutztes Gerät als Waise ausweisen.")
        return 2

    kandidaten = [b for b in befunde if b.ist_kandidat]
    print(f"{len(befunde)} gepatchte Geräte, {len(kandidaten)} ohne jede Referenz.")
    print(f"Geprüfte Referenz-Orte: {', '.join(patch_dedup.SCAN_ORTE)}")
    print()
    for b in befunde:
        if b.ist_kandidat or args.alle:
            print(_zeile(b))

    if not kandidaten:
        print("\nNichts zu tun.")
        return 0
    if not args.anwenden:
        print(f"\nNichts verändert. Zum Verschieben: --anwenden")
        return 0

    verschoben = patch_dedup.in_quarantaene(
        state, [b.fid for b in kandidaten], grund="tools/patch_quarantaene.py")
    print(f"\n{len(verschoben)} Gerät(e) verschoben: {verschoben}")
    if len(verschoben) < len(kandidaten):
        print("Einige Kandidaten wurden beim zweiten Scan doch noch referenziert "
              "und blieben stehen.")
    print("Zurückholen: --zurueck <fid>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
