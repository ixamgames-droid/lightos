"""DOC-16: Anleitungsbilder reproduzierbar aus dem Code erzeugen.

Einstieg ist ``tools/anleitungsbilder.py`` (CLI). Dieses Paket haelt die
Bausteine:

* :mod:`.sandbox`   — lenkt ALLE Datenpfade in einen Wegwerf-Ordner um, bevor
  irgendein ``src``-Modul geladen wird, und prueft das vor dem ersten Bild.
* :mod:`.demo_show` — die Doku-Demo-Show, nur aus eingebauten Generic-Profilen.
* :mod:`.marker`    — roter Rahmen + Nummernkreis per QPainter.
* :mod:`.runner`    — Szenen abarbeiten, Bilder und ``bilder.json`` schreiben.
* ``szenen_<anleitung>.py`` — je Anleitung die Liste ``SZENEN``.

Wichtig: Dieses ``__init__`` importiert bewusst NICHTS aus ``src`` — sonst liefe
ein Import an der Sandbox vorbei (``fixture_db.DB_PATH`` und
``app_state.SHOW_DB_PATH`` werden beim ersten Import eingefroren).
"""
