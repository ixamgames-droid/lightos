ID: XPLAT-62
Prioritaet: P2
Status: todo
Titel: Linux-Installation wie ein normales Programm: .deb-Paket fuer Mint/Ubuntu/Debian, AppImage fuer andere Distributionen

**Herkunft:** Entscheidung des Projektinhabers vom 22.11.2026 (DOC-68: am Ende ein richtiger Installer). Heute gibt es unter Linux nur `install.py` aus dem Quellcode und die udev-Regel `packaging/linux/60-lightos-udmx.rules`.

**Ziel:** (1) **.deb-Paket** als Hauptweg fuer Linux Mint, Ubuntu und Debian (der Projektinhaber nutzt Mint): Doppelklick bzw. `apt install ./lightos_<version>.deb`, Eintrag im Startmenue mit Symbol, Programm unter /opt/lightos mit eigener Python-Laufzeit (PyInstaller-Ordner wie unter Windows), udev-Regeln fuer uDMX/Enttec mitinstallieren und den Benutzer auf die Gruppe `dialout` hinweisen, sauber deinstallierbar; Benutzerdaten bleiben in ~/.local/share/LightOS. (2) **AppImage** als Ein-Datei-Weg fuer alle anderen Distributionen (ohne Installation startbar, udev-Hinweis im ersten Start). Flatpak/Snap bewusst nicht: deren Sandbox erschwert den Zugriff auf USB-DMX, serielle Ports und MIDI. (3) Bau beider Pakete im GitHub-Workflow wie das Windows-Setup, Pruefung in einer frischen Mint-/Ubuntu-VM bzw. einem Container (Installieren, Starten, Deinstallieren).

**Erledigt, wenn:** .deb und AppImage aus dem Workflow entstehen, auf einem frischen Mint installiert/gestartet/entfernt werden koennen, USB-DMX ohne Handarbeit (ausser Gruppe dialout) funktioniert, INSTALL.md beide Wege beschreibt.
