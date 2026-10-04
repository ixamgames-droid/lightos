"""Fixture-Browser Dialog — Gerät aus DB wählen und patchen."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QComboBox,
    QSpinBox, QFormLayout, QGroupBox, QMessageBox, QSplitter
)
from PySide6.QtCore import Qt
from src.core.database import fixture_db as fdb
from src.core.database.models import FixtureProfile, PatchedFixture

_UNIVERSE_MIN = 1

#: UI-64(e): lesbare Typnamen fuer die „Typ"-Spalte. Die Datenbank fuehrt
#: Bezeichner wie ``moving_head`` — in einer 80-px-Spalte wurde daraus
#: „moving_h…". Unbekannte Typen bekommen per ``typ_anzeige`` einen
#: lesbaren Rueckfall statt des rohen Bezeichners.
_TYP_NAMEN = {
    "moving_head": "Moving Head",
    "par":         "PAR",
    "led_bar":     "LED-Bar",
    "par_bar":     "PAR-Bar",
    "strobe":      "Strobe",
    "dimmer":      "Dimmer",
    "scanner":     "Scanner",
    "laser":       "Laser",
    "matrix":      "Matrix",
    "smoke":       "Nebel",
    "hazer":       "Hazer",
    "other":       "Sonstiges",
}


def typ_anzeige(fixture_type: str | None) -> str:
    """UI-64(e): Datenbank-Typ -> Anzeige-Text der „Typ"-Spalte."""
    roh = (fixture_type or "").strip()
    if not roh:
        return ""
    return _TYP_NAMEN.get(roh.lower(), roh.replace("_", " ").title())
_UNIVERSE_MAX = 32


#: UI-74: ``herkunft.art`` einer Profil-Datei -> Zusatz in der Herkunftszeile.
_ART_ZUSATZ = {
    "qlcplus": "aus QLC+, überarbeitet",
    "ofl": "aus der Open Fixture Library, überarbeitet",
    "hersteller-handbuch": "nach Herstellerhandbuch",
    "lightos": "eigene Erstellung",
}


def herkunft_zeile(profil, download: dict | None = None) -> tuple[str, str]:
    """UI-74: eine kurze Zeile „woher kommt dieses Profil, ist es geprueft?“
    fuer die Geraeteauswahl — und ein Tooltip mit den Einzelheiten.

    Quellen in dieser Reihenfolge: die gespeicherte Herkunft
    (``FixtureProfile.herkunft``, FM-56), der Download-Nachweis
    (``profil_herkunft``, FM-53, als ``download`` hereingereicht) und zuletzt
    ``source``. „geprüft ✓“ steht nur, wenn die Datei ``geprueft.ok`` sagt —
    laut SCHEMA.md heisst das: Kanal fuer Kanal am Geraet oder gegen das
    Handbuch geprueft. Alles andere ist „ungeprüft“, auch ein Builtin."""
    from src.core.database import bibliothek_format as BF
    src = (getattr(profil, "source", "") or "").lower()
    try:
        gesp = BF.gespeicherte_herkunft(profil)
    except Exception:
        gesp = None
    art = ((gesp or {}).get("herkunft") or {}).get("art", "")
    zusatz = _ART_ZUSATZ.get(art, "")
    if src == "lightos":
        wer = "LightOS-Bibliothek" + (f" ({zusatz})" if zusatz else "")
    elif src == "builtin":
        wer = "LightOS (eingebaut)"
    elif src == "user":
        wer = "eigenes Profil" + (f" ({zusatz})" if zusatz and art != "lightos" else "")
    elif src == "qlcplus":
        if download:
            wer = (f"QLC+-Bibliothek, heruntergeladen "
                   f"({download.get('lizenz') or 'Lizenz unbekannt'})")
        else:
            wer = "QLC+-Import"
    else:
        wer = src or "unbekannt"
    geprueft = bool(((gesp or {}).get("geprueft") or {}).get("ok"))
    text = f"Herkunft: {wer} · " + ("geprüft ✓" if geprueft else "ungeprüft")
    tipp: list[str] = []
    if gesp:
        titel = (gesp.get("quelle") or {}).get("titel", "")
        if titel:
            tipp.append(f"Quelle: {titel}")
        lizenz = (gesp.get("herkunft") or {}).get("lizenz", "")
        if lizenz:
            tipp.append(f"Lizenz: {lizenz}")
        wie = (gesp.get("geprueft") or {}).get("wie", "")
        if wie:
            tipp.append(f"Prüfung: {wie}")
    elif download:
        tipp.append(f"Quelle: {download.get('quelle', '')}")
        tipp.append(f"Lizenz: {download.get('lizenz', '')}")
    return text, "\n".join(t for t in tipp if t.split(": ", 1)[-1])


def download_herkunft(fixture_id: int, eng=None) -> dict | None:
    """UI-74: der Download-Nachweis eines Profils (FM-53) — NUR lesend.

    ``bibliothek_download.herkunft_lesen`` legt die Tabelle bei Bedarf an; in
    einer Auswahlliste darf das Anklicken eines Geraets nicht in die
    Fixture-DB schreiben. Fehlt die Tabelle, gibt es eben keinen Nachweis."""
    from sqlalchemy import text as _sql
    try:
        if eng is None:
            eng = fdb.engine()
        with eng.connect() as conn:
            zeile = conn.execute(_sql(
                "SELECT quelle, lizenz FROM profil_herkunft WHERE fixture_id = :i"),
                {"i": int(fixture_id)}).first()
    except Exception:
        return None
    return {"quelle": zeile[0], "lizenz": zeile[1]} if zeile else None


def universum_vorschlag(fixtures) -> int:
    """UI-50: welches Universum der Patch-Dialog vorbelegen soll —
    **das Universum des zuletzt gepatchten Geraets, sonst 1.**

    Bis UI-50 startete das Feld immer auf 1. Wer sein Rig auf Universum 3
    faehrt, korrigierte es bei JEDEM Geraet von Hand; wer es vergass, patchte
    auf ein Universum ohne Ausgang und suchte den Fehler danach am Rig.

    **Warum diese Regel** (drei standen zur Wahl — zuletzt benutzt, das mit den
    meisten Geraeten, das des ausgewaehlten Fixtures): Ein Rig wird blockweise
    gepatcht, ein Universum nach dem anderen. Der letzte Patch ist damit die
    beste Vorhersage fuer den naechsten. Die Mehrheitsregel wuerde beim Wechsel
    in ein neues Universum jedes Mal ins alte zurueckspringen — genau dort, wo
    der Anwender gerade NICHT mehr ist. Und das ausgewaehlte Fixture sagt ueber
    sein Universum gar nichts: die Auswahl kommt aus der geraeteweiten
    Bibliothek, nicht aus dem Patch.

    **„Zuletzt gepatcht" = groesste fid.** ``AppState.next_fid()`` vergibt die
    fid streng aufsteigend (Maximum + 1), das juengste Geraet hat also immer die
    groesste — unabhaengig davon, in welcher Reihenfolge der Patch-Cache
    gerade sortiert ist. Diese Unabhaengigkeit ist eigens belegt
    (``test_unsortierte_eingabe_aendert_den_vorschlag_nicht``): ueber den
    Dialog allein waere sie NICHT nachweisbar, weil ``_reload_patch_cache``
    mit ``order_by(fid)`` laedt — dort sind „groesste fid" und „letzte Zeile"
    ununterscheidbar, und die Mutation auf ``list(fixtures)[-1]`` ueberlebte
    genau deshalb die erste Testfassung.

    Leerer Patch -> 1: es gibt nichts zu erben. Ebenso bei einem Universum
    ausserhalb des Eingabebereichs (von Hand editierte Show-Datei) — eine
    neutrale 1 ist ehrlicher als eine still auf 32 geklemmte Zahl.

    Voellig unbrauchbare Werte (kein ``fid``, ``universe`` nicht in eine Zahl
    wandelbar) faengt bewusst NUR der Aufrufer ab — ein zweiter Wall hier waere
    toter Code, den kein Test erreicht.
    """
    if not fixtures:
        return _UNIVERSE_MIN
    universum = int(max(fixtures, key=lambda f: f.fid).universe)
    if not _UNIVERSE_MIN <= universum <= _UNIVERSE_MAX:
        return _UNIVERSE_MIN
    return universum



def plane_patch_adressen(universe: int, address: int, ch_count: int, count: int,
                         offset: int, max_univ: int = 32, univ_size: int = 512):
    """Adressen fuer ``count`` Geraete ab (universe, address), Abstand ``offset``.

    EINE Regel fuer ALLE Geraete (FM-39): passt ein Geraet mit seinen
    ``ch_count`` Kanaelen nicht mehr ins Universe, rollt es ins naechste ab
    Adresse 1 — auch das erste. Bis 2026-09-29 lief das erste still ueber
    Kanal 512 hinaus (die letzten Kanaele gingen nirgends hin), die Kopien
    wurden gerollt. Jenseits von ``max_univ`` wird abgebrochen.

    Liefert ``(plan, uebersprungen, gerollt)``: ``plan`` = ``[(universe,
    address), ...]``, ``gerollt`` = Nummern (0-basiert) der Geraete, die
    ins naechste Universe ausweichen mussten — damit die Oberflaeche es sagt.
    """
    ch = max(1, int(ch_count))
    plan: list[tuple[int, int]] = []
    gerollt: list[int] = []
    u, a = int(universe), int(address)
    for i in range(int(count)):
        if i:
            a += int(offset)
        if a + ch - 1 > univ_size:
            u += 1
            a = 1
            gerollt.append(i)
        if u > max_univ or ch > univ_size:
            # dieses und alle folgenden passen nirgends mehr hin
            return plan, int(count) - i, [g for g in gerollt if g < i]
        plan.append((u, a))
    return plan, 0, gerollt

class FixtureBrowserDialog(QDialog):
    def __init__(self, next_fid: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerät hinzufügen")
        self.setMinimumSize(700, 500)
        self.result_fixture: PatchedFixture | None = None
        self._next_fid = next_fid
        self._selected_profile: FixtureProfile | None = None
        self._setup_ui()
        self._load_tree()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Suchleiste
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Suche:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Herstellername, Gerätename, Typ...")
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Geräte-Baum
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Gerät", "Typ", "Kanäle"])
        self._tree.setColumnWidth(0, 280)
        self._tree.setColumnWidth(1, 80)
        self._tree.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self._tree)

        # Rechte Seite: Optionen
        right = QGroupBox("Patch-Optionen")
        form = QFormLayout(right)

        self._lbl_manufacturer = QLabel("—")
        self._lbl_fixture = QLabel("—")
        form.addRow("Hersteller:", self._lbl_manufacturer)
        form.addRow("Gerät:", self._lbl_fixture)
        # UI-74: Herkunft + Pruefstand des gewaehlten Profils — klein und
        # grau, Einzelheiten im Tooltip.
        self._lbl_herkunft = QLabel("")
        self._lbl_herkunft.setWordWrap(True)
        self._lbl_herkunft.setStyleSheet("color: #8b949e; font-size: 11px;")
        form.addRow("", self._lbl_herkunft)

        self._combo_mode = QComboBox()
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Modus:", self._combo_mode)

        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, 64)
        self._spin_count.setValue(1)
        form.addRow("Anzahl:", self._spin_count)

        self._edit_label = QLineEdit()
        form.addRow("Label:", self._edit_label)

        self._spin_universe = QSpinBox()
        self._spin_universe.setRange(_UNIVERSE_MIN, _UNIVERSE_MAX)
        self._spin_universe.setValue(self._universum_vorbelegung())
        form.addRow("Universe:", self._spin_universe)

        self._spin_address = QSpinBox()
        self._spin_address.setRange(1, 512)
        form.addRow("DMX-Adresse:", self._spin_address)
        # P1: Hinweis unter dem Adressfeld — zeigt den automatischen Vorschlag
        # bzw. eine Warnung, wenn kein zusammenhaengender Bereich mehr frei ist.
        self._lbl_addr_hint = QLabel("")
        self._lbl_addr_hint.setWordWrap(True)
        self._lbl_addr_hint.setStyleSheet("color: #8b949e;")
        form.addRow("", self._lbl_addr_hint)
        self._spin_universe.valueChanged.connect(
            lambda _v: self._update_address_suggestion())

        self._spin_offset = QSpinBox()
        self._spin_offset.setRange(0, 64)
        self._spin_offset.setValue(0)
        self._spin_offset.setToolTip("Adress-Abstand zwischen mehreren Geräten (0 = dicht)")
        form.addRow("Adress-Offset:", self._spin_offset)

        splitter.addWidget(right)
        splitter.setSizes([400, 300])
        layout.addWidget(splitter)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        self._btn_add = QPushButton("Hinzufügen")
        self._btn_add.setEnabled(False)
        self._btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self._btn_add)
        layout.addLayout(btn_row)

    def _universum_vorbelegung(self) -> int:
        """UI-50: Quelle der Vorbelegung ist der **Patch** — anders als im
        Ausgabe-Dialog (OUT-50), der aus ``universes.json`` laedt. Der Patch
        sagt, wo das Rig steht; ``universes.json`` sagt nur, was eingerichtet
        ist. Der Import ist wie in ``_update_address_suggestion`` lazy, damit
        der Dialog auch ohne lauffaehigen AppState aufgeht (dann Standard 1).
        """
        try:
            from src.core.app_state import get_state
            return universum_vorschlag(get_state().get_patched_fixtures())
        except Exception:
            return _UNIVERSE_MIN

    def _load_tree(self, query: str = ""):
        self._tree.clear()
        if query:
            fixtures = fdb.search_fixtures(query)
            for f in fixtures:
                mfr_name = f.manufacturer.name if f.manufacturer else "Unbekannt"
                item = QTreeWidgetItem([
                    f"{mfr_name} — {f.name}", typ_anzeige(f.fixture_type),
                    str(f.modes[0].channel_count) if f.modes else "?"
                ])
                item.setToolTip(1, f.fixture_type or "")
                item.setData(0, Qt.ItemDataRole.UserRole, f.id)
                self._tree.addTopLevelItem(item)
        else:
            for mfr in fdb.get_all_manufacturers():
                mfr_item = QTreeWidgetItem([mfr.name, "", ""])
                mfr_item.setData(0, Qt.ItemDataRole.UserRole, None)
                fixtures = fdb.get_fixtures_by_manufacturer(mfr.id)
                for f in fixtures:
                    ch = str(f.modes[0].channel_count) if f.modes else "?"
                    child = QTreeWidgetItem([f.name, typ_anzeige(f.fixture_type), ch])
                    child.setToolTip(1, f.fixture_type or "")
                    child.setData(0, Qt.ItemDataRole.UserRole, f.id)
                    mfr_item.addChild(child)
                if fixtures:
                    self._tree.addTopLevelItem(mfr_item)
            self._tree.expandAll()
        self._typ_spalte_anpassen()

    def _typ_spalte_anpassen(self):
        """UI-64(e): Typ-Spalte so breit wie ihr laengster Eintrag (nie
        schmaler als die bisherigen 80 px), damit nichts mehr mit „…" endet.

        Bewusst selbst gemessen statt ``resizeColumnToContents``: das sieht
        nur die gerade sichtbaren Zeilen an, und bei rund 1800 Geraeten steht
        der breiteste Typ selten oben."""
        fm = self._tree.fontMetrics()
        texte = {"Typ"}
        stack = [self._tree.topLevelItem(i)
                 for i in range(self._tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            texte.add(it.text(1))
            stack.extend(it.child(j) for j in range(it.childCount()))
        breite = max(fm.horizontalAdvance(t) for t in texte) + 24
        self._tree.setColumnWidth(1, max(80, breite))

    def _on_search(self, text: str):
        self._load_tree(text.strip())

    def _on_selection(self, current, _previous):
        if not current:
            return
        fid = current.data(0, Qt.ItemDataRole.UserRole)
        if fid is None:
            return
        profile = fdb.get_fixture(fid)
        if not profile:
            return
        self._selected_profile = profile
        self._lbl_manufacturer.setText(
            profile.manufacturer.name if profile.manufacturer else "—"
        )
        self._lbl_fixture.setText(profile.name)
        text, tipp = herkunft_zeile(profile, download_herkunft(profile.id))
        self._lbl_herkunft.setText(text)
        self._lbl_herkunft.setToolTip(tipp)
        self._combo_mode.clear()
        modes = fdb.get_modes(profile.id)
        for m in modes:
            self._combo_mode.addItem(f"{m.name} ({m.channel_count}ch)", m.id)
        self._edit_label.setText(profile.short_name or profile.name)
        self._btn_add.setEnabled(True)

    def _on_mode_changed(self, _idx):
        self._update_address_suggestion()

    def _current_channel_count(self) -> int:
        mode_id = self._combo_mode.currentData()
        if not mode_id:
            return 0
        try:
            return len(fdb.get_channels(mode_id))
        except Exception:
            return 0

    def _update_address_suggestion(self):
        """P1: naechsten freien zusammenhaengenden Kanalbereich vorschlagen
        (zentrale Logik: AppState.suggest_address — lueckenbewusst, pro
        Universum). Kein Platz -> deutliche Warnung statt stillem Konflikt."""
        ch_count = self._current_channel_count()
        if ch_count <= 0:
            return
        try:
            from src.core.app_state import get_state
            suggestion = get_state().suggest_address(
                self._spin_universe.value(), ch_count)
        except Exception:
            return
        if suggestion is None:
            self._lbl_addr_hint.setText(
                f"⚠ Kein freier zusammenhängender Bereich für {ch_count} "
                f"Kanäle in Universe {self._spin_universe.value()} — bitte "
                f"anderes Universum wählen oder Patch aufräumen.")
            self._lbl_addr_hint.setStyleSheet("color: #f85149;")
        else:
            self._spin_address.setValue(suggestion)
            self._lbl_addr_hint.setText(
                f"Vorschlag: Adresse {suggestion} "
                f"(nächster freier Bereich für {ch_count} Kanäle)")
            self._lbl_addr_hint.setStyleSheet("color: #8b949e;")

    def _on_add(self):
        if not self._selected_profile:
            return
        mode_id = self._combo_mode.currentData()
        mode_name = self._combo_mode.currentText().split(" (")[0]
        channels = fdb.get_channels(mode_id) if mode_id else []
        ch_count = len(channels)
        auto_dual_tilt = fdb.should_auto_mark_dual_tilt(
            self._selected_profile, channels)
        count = self._spin_count.value()
        universe = self._spin_universe.value()
        address = self._spin_address.value()
        offset = self._spin_offset.value() or ch_count
        label_base = self._edit_label.text() or self._selected_profile.name
        fid = self._next_fid

        # FM-39: EINE Regel fuer das erste Geraet und die Kopien (vorher lief das
        # erste still ueber Kanal 512 hinaus, die Kopien wurden gerollt).
        plan, self.skipped_count, self.gerollt = plane_patch_adressen(
            universe, address, ch_count, count, offset)
        if not plan:
            self.result_fixture = None
            self.extra_fixtures = []
            self.accept()
            return
        universe, address = plan[0]

        # Bei mehreren Geräten: erstes zurückgeben (weitere werden in patch_view hinzugefügt)
        self.result_fixture = PatchedFixture(
            fid=fid,
            label=label_base if count == 1 else f"{label_base} 1",
            fixture_profile_id=self._selected_profile.id,
            mode_name=mode_name,
            universe=universe,
            address=address,
            channel_count=ch_count,
            manufacturer_name=self._selected_profile.manufacturer.name if self._selected_profile.manufacturer else "",
            fixture_name=self._selected_profile.name,
            fixture_type=self._selected_profile.fixture_type,
            spider_dual_tilt=auto_dual_tilt,
        )
        # Zusatz-Geräte als Liste mitgeben (Adressen aus demselben Plan).
        self.extra_fixtures = []
        for i, (cur_univ, cur_addr) in enumerate(plan[1:], start=1):
            self.extra_fixtures.append(PatchedFixture(
                fid=fid + i,
                label=f"{label_base} {i + 1}",
                fixture_profile_id=self._selected_profile.id,
                mode_name=mode_name,
                universe=cur_univ,
                address=cur_addr,
                channel_count=ch_count,
                manufacturer_name=self._selected_profile.manufacturer.name if self._selected_profile.manufacturer else "",
                fixture_name=self._selected_profile.name,
                fixture_type=self._selected_profile.fixture_type,
                spider_dual_tilt=auto_dual_tilt,
            ))
        self.accept()
