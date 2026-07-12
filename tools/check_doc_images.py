"""DOC-10 Anleitungs-/Bild-Audit: findet TOTE Bild-Links in der Doku.

Durchsucht alle Markdown-Dateien unter docs/ (und README.md) nach Bild-Referenzen —
Markdown ``![alt](pfad)`` UND HTML ``<img src="pfad">`` — und prueft, ob der (relativ
zur jeweiligen .md-Datei aufgeloeste) Pfad existiert. Externe (http/https/data:) und
Anker werden uebersprungen.

Exit 0 = keine toten Links, Exit 1 = tote Links gefunden (CI-tauglich).
  python tools/check_doc_images.py            # Report auf stdout
  python tools/check_doc_images.py --list-ok  # zusaetzlich OK-Zaehler je Datei
"""
import os
import re
import sys
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MD_IMG = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")   # ![alt](pfad "title")
HTML_IMG = re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)   # auskommentierte Bilder ignorieren
# Code-Bloecke/-Spans enthalten oft Bild-SYNTAX-Beispiele (z.B. `![alt](pfad)` im
# Audit-Report), keine echten Referenzen -> vor dem Scan entfernen.
CODE_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _iter_md_files():
    for base, _dirs, files in os.walk(os.path.join(REPO, "docs")):
        for fn in files:
            if fn.lower().endswith(".md"):
                yield os.path.join(base, fn)
    readme = os.path.join(REPO, "README.md")
    if os.path.exists(readme):
        yield readme


def _refs(text):
    for m in MD_IMG.finditer(text):
        yield m.group(1)
    for m in HTML_IMG.finditer(text):
        yield m.group(1)


def scan():
    """Prueft alle Doku-Bild-Referenzen. Liefert (total_refs, dead, per_file_ok).
    dead = Liste (md_relpath, ref, resolved_relpath) fehlender Bilder."""
    total_refs = 0
    dead = []          # (md_relpath, ref, resolved_relpath)
    per_file_ok = {}
    for md in _iter_md_files():
        try:
            text = open(md, "r", encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        text = HTML_COMMENT.sub("", text)      # auskommentierte Bilder nicht pruefen
        text = CODE_FENCE.sub("", text)        # Bild-Syntax in ```-Bloecken ist Beispiel
        text = INLINE_CODE.sub("", text)       # `![](…)`-Beispiele nicht als Ref werten
        md_dir = os.path.dirname(md)
        ok = 0
        for ref in _refs(text):
            r = ref.strip()
            if r.startswith(("http://", "https://", "data:", "#", "mailto:")):
                continue
            r = urllib.parse.unquote(r.split("#", 1)[0].split("?", 1)[0])
            if not r:
                continue
            total_refs += 1
            target = os.path.normpath(os.path.join(md_dir, r))
            if os.path.exists(target):
                ok += 1
            else:
                dead.append((os.path.relpath(md, REPO).replace("\\", "/"),
                             ref, os.path.relpath(target, REPO).replace("\\", "/")))
        if ok:
            per_file_ok[os.path.relpath(md, REPO).replace("\\", "/")] = ok
    return total_refs, dead, per_file_ok


def find_dead_links():
    """Nur die Liste der toten Bild-Links (fuer Tests)."""
    return scan()[1]


def main() -> int:
    list_ok = "--list-ok" in sys.argv
    total_refs, dead, per_file_ok = scan()

    print(f"[doc-images] {total_refs} Bild-Referenzen geprueft, "
          f"{len(dead)} tot, in {len(per_file_ok)} Dateien mit Bildern.")
    if list_ok:
        for f, n in sorted(per_file_ok.items()):
            print(f"  ok {n:3d}  {f}")
    if dead:
        print("\n[doc-images] TOTE Bild-Links:")
        for md_rel, ref, target in dead:
            print(f"  {md_rel}\n      ref: {ref}\n      -> fehlt: {target}")
        return 1
    print("[doc-images] keine toten Bild-Links.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
