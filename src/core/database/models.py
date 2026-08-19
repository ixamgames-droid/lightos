"""SQLAlchemy ORM-Modelle für Fixture-DB und Show-Daten."""
from __future__ import annotations
from sqlalchemy import (
    String, Integer, Boolean, ForeignKey, Text, Float, create_engine
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, Session
)


class Base(DeclarativeBase):
    pass


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    short_name: Mapped[str] = mapped_column(String(20), default="")

    fixtures: Mapped[list[FixtureProfile]] = relationship(back_populates="manufacturer")

    def __repr__(self) -> str:
        return f"<Manufacturer {self.name}>"


class FixtureProfile(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"))
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str] = mapped_column(String(40), default="")
    fixture_type: Mapped[str] = mapped_column(String(40), default="other")
    power_w: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="builtin")
    # FM-12: expliziter 3D-Modell-Override fuer den Visualizer ("" = Automatik:
    # Kanal-Heuristik viz_model_for bzw. fixture_type entscheidet).
    viz_model: Mapped[str] = mapped_column(String(40), default="")

    manufacturer: Mapped[Manufacturer] = relationship(back_populates="fixtures")
    modes: Mapped[list[FixtureMode]] = relationship(
        back_populates="fixture", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Fixture {self.name}>"


class FixtureMode(Base):
    __tablename__ = "fixture_modes"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    name: Mapped[str] = mapped_column(String(80))
    channel_count: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    # VIZ-50a: PHYSISCHE Rasterform eines Pixel-Panels in DIESEM Modus —
    # Zeilen x Spalten der Zonen/Pixel. ``0`` (beide) = nicht hinterlegt; dann
    # raet der Renderer die Form wie bisher near-square aus der Pixelzahl
    # (`panelGrid`), und nichts aendert sich.
    #
    # ★ Warum am MODUS und nicht am gepatchten Geraet: die Rasterform ist eine
    #   Aussage ueber das MODELL. Jedes Exemplar eines ZQ06121 ist 4x12; was
    #   sich von Exemplar zu Exemplar unterscheidet, ist die Nummerierung
    #   (`pixel_order`, Geraetemenue) und die Montage (`element_rotation`) —
    #   beides sitzt deshalb zu Recht auf ``PatchedFixture``. Und am Modus statt
    #   am Profil, weil die Pixelzahl modusabhaengig ist (ZQ06121: 154ch/144ch;
    #   Stairville: 8ch = 1 Zone, 432ch = 144 Pixel).
    #
    # ★ Warum zwei Zahlen und kein ``layout_json``: rows/cols beantwortet genau
    #   die Frage, die `panelGrid` heute raet — nicht mehr. Ein Band-JSON muesste
    #   zusaetzlich beantworten, WO die Warmweiss-Segmente sitzen (VIZ-50b);
    #   dieser Verbraucher existiert noch nicht, und ein Format ohne Verbraucher
    #   ist ungeprueft. Sackgasse ist die Zahlenfassung nicht: ein spaeteres
    #   Bandformat hat ein Einheitsraster, aus dem rows/cols folgen.
    grid_rows: Mapped[int] = mapped_column(Integer, default=0)
    grid_cols: Mapped[int] = mapped_column(Integer, default=0)
    # ★ CDX-52: Rasterform der EIGENEN Weiss-Segmente desselben Modus — die
    # Warmweiss-Leiste, die NICHT auf dem Farbraster liegt (ZQ06121: eine Reihe
    # quer ueber die Mitte). ``0`` (beide) = keine eigene Leiste hinterlegt;
    # dann gibt es im 3D auch keine.
    #
    # ★ Warum das nicht abgeleitet werden kann — und warum es die Kanalzahl
    #   NICHT tut: ``0 < color_w < color_r`` war bis CDX-52 die Regel, und eine
    #   Kanalzahl traegt keine Ortsangabe. Dieselbe Signatur (48x ``color_r`` +
    #   8x ``color_w``) passt auf mindestens drei physisch verschiedene Geraete:
    #   auf eine eigene Leiste (ZQ06121), auf acht Weiss-LEDs, die IN den Zonen
    #   sitzen und je sechs davon teilen, und auf ein Geraet mit einem globalen
    #   Weiss, das in acht Dimmabschnitte zerfaellt. Welches davon vorliegt,
    #   entscheidet der Blick aufs Geraet — beim ZQ06121 Robins Messung vom
    #   2026-08-05. Die stand bis dahin nur in einem Quellkommentar.
    #
    # ★ Warum ZWEI Zahlen wie oben und nicht eine Ja/Nein-Marke: die Leiste hat
    #   eine Form. ``panelGrid`` fuellt die fehlende der beiden aus der Zahl der
    #   ``color_w``-Kanaele — der ZQ06121 traegt deshalb (1, 0) und NICHT (1, 8):
    #   die 8 stehen in den Kanaelen, und eine Kopie davon liefe still daneben
    #   (FM16E). Hinterlegt wird nur, was die Kanaele nicht sagen koennen.
    white_rows: Mapped[int] = mapped_column(Integer, default=0)
    white_cols: Mapped[int] = mapped_column(Integer, default=0)

    fixture: Mapped[FixtureProfile] = relationship(back_populates="modes")
    channels: Mapped[list[FixtureChannel]] = relationship(
        back_populates="mode", cascade="all, delete-orphan",
        order_by="FixtureChannel.channel_number"
    )


class FixtureChannel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    mode_id: Mapped[int] = mapped_column(ForeignKey("fixture_modes.id"))
    channel_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80))
    attribute: Mapped[str] = mapped_column(String(40), default="raw")
    default_value: Mapped[int] = mapped_column(Integer, default=0)
    highlight_value: Mapped[int] = mapped_column(Integer, default=255)
    invert: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[str] = mapped_column(String(20), default="8bit")

    mode: Mapped[FixtureMode] = relationship(back_populates="channels")
    ranges: Mapped[list[ChannelRange]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class ChannelRange(Base):
    __tablename__ = "channel_ranges"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    range_from: Mapped[int] = mapped_column(Integer)
    range_to: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80))
    # Maschinen-lesbare Kategorie (M1.2): "open" / "closed" / "strobe" / "color" /
    # "gobo" / "rotate" / "shake" / "sound" / "reset" / "" (unbekannt). Erlaubt
    # generische Schnellwahl (Shutter-Open erkennen, Gobo-/Farb-Slots auflisten).
    kind: Mapped[str] = mapped_column(String(20), default="")

    channel: Mapped[FixtureChannel] = relationship(back_populates="ranges")


# ── Show-Daten (in Show-Datei gespeichert, nicht in Fixture-DB) ──────────────

class PatchedFixture(Base):
    __tablename__ = "patched_fixtures"

    id: Mapped[int] = mapped_column(primary_key=True)
    fid: Mapped[int] = mapped_column(Integer, unique=True)
    label: Mapped[str] = mapped_column(String(80))
    fixture_profile_id: Mapped[int] = mapped_column(Integer)
    mode_name: Mapped[str] = mapped_column(String(80))
    universe: Mapped[int] = mapped_column(Integer, default=1)
    address: Mapped[int] = mapped_column(Integer)
    channel_count: Mapped[int] = mapped_column(Integer)
    invert_pan: Mapped[bool] = mapped_column(Boolean, default=False)
    invert_tilt: Mapped[bool] = mapped_column(Boolean, default=False)
    swap_pan_tilt: Mapped[bool] = mapped_column(Boolean, default=False)
    dimmer_curve: Mapped[str] = mapped_column(String(20), default="linear")
    # Spider-Doppelbar: ist die 2. Farbreihe gespiegelt (W,B,G,R) statt parallel
    # (R,G,B,W)? Rein visuell (3D-Visualizer) — DMX unveraendert. Default gespiegelt.
    spider_mirrored: Mapped[bool] = mapped_column(Boolean, default=True)
    # Spider/Dual-Tilt: dieses Geraet explizit als Doppel-Tilt-Spider behandeln
    # (zwei Tilt-Bars, KEIN echtes Pan). Wenn True, deutet get_channels_for_patched
    # den Pan-Motor als zweiten Tilt-Kopf um -> Position-/EFX-Tab schalten auf die
    # Spider-Bedienung (Motoren-Regler statt XY-Pad, Bewegungsmuster statt Kreise).
    # Fuer fehl-importierte QXF-Spider, deren zwei Motoren als pan/tilt statt
    # tilt/tilt gemappt wurden. Auto-Erkennung ist unmoeglich (echte Pan+Tilt-Mover
    # sehen strukturell identisch aus), daher setzt der Nutzer es bewusst im Patch.
    spider_dual_tilt: Mapped[bool] = mapped_column(Boolean, default=False)
    # FM-HEADLAYOUT: WIE ein Mehrkopf-Geraet (Spider/Mover-Bar/Hydrabeam) programmiert
    # werden soll. Steuert, ob beim Patchen automatisch die Pro-Kopf-Matrix-Gruppe
    # ("… · Köpfe", create_head_matrix_group) angelegt wird:
    #   "auto"   = Bestandsverhalten (Gruppe wird automatisch angelegt) — DEFAULT,
    #              damit Alt-Shows sich exakt wie bisher verhalten.
    #   "heads"  = Koepfe einzeln: die Kopf-Matrix-Gruppe SOLL existieren (wird beim
    #              Speichern idempotent angelegt/wiederhergestellt).
    #   "single" = als EINE Lampe: keine automatische Kopf-Matrix-Gruppe.
    # WICHTIG: der Modus loescht NIE eine bestehende Gruppe (zusammengelegte/
    # bearbeitete Matrizen bleiben unangetastet) — "single" verhindert nur das
    # automatische Neuanlegen.
    head_mode: Mapped[str] = mapped_column(String(16), default="auto")
    # FM-13: In WELCHER raeumlichen Reihenfolge legt DIESES Panel seine Pixel auf
    # DMX? Das Profil sagt es nicht — die ADJ Dotz Matrix nummeriert im
    # Werkszustand in Schlangenlinien, am Geraet umstellbar ("Pixel Flip").
    # Darum eine Eigenschaft des gepatchten Geraets, nicht des Profils.
    # Werte/Umrechnung im Leaf-Modul core.pixel_order; "rowwise" = Bestand.
    pixel_order: Mapped[str] = mapped_column(String(16), default="rowwise")
    # ORIENT: wie das Panel HAENGT — unabhaengig davon, wie es NUMMERIERT.
    # Ein Panel kann in Schlangenlinien zaehlen UND hochkant montiert sein;
    # `pixel_order` kann das nicht ausdruecken, weil es ausschliesslich die
    # Spalte aendert (nie die Zeile) und das Raster nie umformt.
    # 0/90/180/270 im Uhrzeigersinn, danach optional waagerecht gespiegelt.
    element_rotation: Mapped[int] = mapped_column(Integer, default=0)
    element_flip: Mapped[bool] = mapped_column(Boolean, default=False)
    # Moving-Head physische Pan/Tilt-Bereiche (Grad) + DMX-Nullpunkt (Mitte) —
    # fuer hardware-genaues Auto-Aim UND den 3D-Visualizer (gleiche Abbildung).
    # Default: typische Moving-Head-Werte 540/270, Mitte bei DMX 128.
    pan_range_deg: Mapped[int] = mapped_column(Integer, default=540)
    tilt_range_deg: Mapped[int] = mapped_column(Integer, default=270)
    pan_zero_dmx: Mapped[int] = mapped_column(Integer, default=128)
    tilt_zero_dmx: Mapped[int] = mapped_column(Integer, default=128)

    # LAS-04: Ausgabe-Protokoll des Geraets. "dmx" (Default) = klassischer
    # DMX-Adressraum (universe/address gelten). Netzwerk-Laser ("etherdream",
    # "idn") haben KEINEN DMX-Adressraum: universe/address sind bedeutungslos,
    # die Render-/Flush-Pfade ueberspringen sie (fixture_uses_dmx) — ihre
    # Programmer-Werte liest spaeter ein eigener LaserOutputManager (LAS-05).
    protocol: Mapped[str] = mapped_column(String(20), default="dmx")
    # LAS-05: Zieladresse (IP/Hostname) fuer Netzwerk-Laser; leer bei DMX.
    net_host: Mapped[str] = mapped_column(String(120), default="")

    # Denormalisiert für schnellen Zugriff ohne JOIN
    manufacturer_name: Mapped[str] = mapped_column(String(120), default="")
    fixture_name: Mapped[str] = mapped_column(String(120), default="")
    fixture_type: Mapped[str] = mapped_column(String(40), default="other")


class FixtureGroup(Base):
    """Spatial grouping of fixtures on a 2D grid (used by RGB Matrix)."""
    __tablename__ = "fixture_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), default="Neue Gruppe")
    cols: Mapped[int] = mapped_column(Integer, default=8)
    rows: Mapped[int] = mapped_column(Integer, default=8)
    # JSON serialized dict {"<col>,<row>": fid, ...}
    positions_json: Mapped[str] = mapped_column(Text, default="{}")
    # FLD-01b: "/"-getrennter Ordnerpfad (z. B. "Front/Wash"); "" = Wurzel.
    folder: Mapped[str] = mapped_column(String(200), default="")


class QuarantinedFixture(Base):
    """STAB-DEDUP-OPT: Ablage fuer verwaiste Patch-Zeilen — verschoben, NICHT
    geloescht.

    ``daten_json`` haelt die VOLLSTAENDIGE Ursprungszeile. Bewusst ein
    JSON-Feld statt gespiegelter Spalten: eine gespiegelte Tabelle driftet,
    sobald ``patched_fixtures`` eine Spalte dazubekommt — und gemerkt wird das
    erst beim Zurueckholen, also genau dann, wenn der Nutzer seine Daten
    zurueck WILL. Die vier ausgeschriebenen Felder sind nur fuer die Anzeige
    da (Liste ohne JSON-Parsen).
    """
    __tablename__ = "quarantined_fixtures"

    id: Mapped[int] = mapped_column(primary_key=True)
    fid: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(80), default="")
    universe: Mapped[int] = mapped_column(Integer, default=1)
    address: Mapped[int] = mapped_column(Integer, default=1)
    grund: Mapped[str] = mapped_column(String(200), default="")
    verschoben_am: Mapped[str] = mapped_column(String(40), default="")
    daten_json: Mapped[str] = mapped_column(Text, default="{}")


# FM-HEADLAYOUT: gueltige Werte + Normalisierer von PatchedFixture.head_mode
# liegen im Leaf-Modul `src/core/head_mode.py` (HEAD_MODES /
# normalize_head_mode) — dort zyklenfrei UND auch dann importierbar, wenn Tests
# dieses models-Modul ausstubben.


def migrate_show_db(engine) -> None:
    """Idempotente Light-Migrationen fuer bestehende Show-DBs (current_show.db).
    create_all() legt fehlende TABELLEN an, aber keine fehlenden SPALTEN — daher
    hier per ALTER TABLE nachziehen, ohne bestehende Daten zu verlieren."""
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(fixture_groups)"))}
            # Tabelle existiert (cols nicht leer), aber noch ohne 'folder' -> ergaenzen.
            if cols and "folder" not in cols:
                conn.execute(text(
                    "ALTER TABLE fixture_groups ADD COLUMN folder VARCHAR DEFAULT ''"))
            # Spider-Doppelbar: Spalte spider_mirrored (Default gespiegelt = 1).
            pcols = {row[1] for row in conn.execute(text("PRAGMA table_info(patched_fixtures)"))}
            if pcols and "spider_mirrored" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN spider_mirrored BOOLEAN DEFAULT 1"))
            # Spider/Dual-Tilt-Marker (Pan-Motor als zweiter Tilt umdeuten).
            if pcols and "spider_dual_tilt" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN spider_dual_tilt BOOLEAN DEFAULT 0"))
            # FM-HEADLAYOUT: Mehrkopf-Programmiermodus (auto|heads|single). Default
            # 'auto' = Bestandsverhalten -> Alt-Shows verhalten sich unveraendert.
            if pcols and "head_mode" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN head_mode "
                    "VARCHAR(16) DEFAULT 'auto'"))
            # Pan/Tilt physische Bereiche + Nullpunkt (Moving-Head-Aim/Visualizer).
            for _col, _def in (("pan_range_deg", 540), ("tilt_range_deg", 270),
                               ("pan_zero_dmx", 128), ("tilt_zero_dmx", 128)):
                if pcols and _col not in pcols:
                    conn.execute(text(
                        f"ALTER TABLE patched_fixtures ADD COLUMN {_col} INTEGER DEFAULT {_def}"))
            # LAS-04: Ausgabe-Protokoll (dmx | etherdream | idn).
            if pcols and "protocol" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN protocol "
                    "VARCHAR(20) DEFAULT 'dmx'"))
            # LAS-05: Netzwerk-Zieladresse fuer Streaming-Laser.
            if pcols and "net_host" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN net_host "
                    "VARCHAR(120) DEFAULT ''"))
            # FM-13: Pixel-Reihenfolge eines Matrix-Panels. Kam mit PR #514 ins
            # Modell, aber NICHT hierher — jede vorher angelegte Show-DB war damit
            # gar nicht mehr ladbar (`_reload_patch_cache` fragt alle Modell-
            # Spalten ab und stirbt an "no such column"). Default 'rowwise' =
            # Bestandsverhalten.
            if pcols and "pixel_order" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN pixel_order "
                    "VARCHAR(16) DEFAULT 'rowwise'"))
            # ORIENT: Montage-Orientierung. GLEICHZEITIG mit der Modell-Spalte
            # hier eingetragen — genau das wurde bei `pixel_order` (PR #514)
            # versaeumt, und jede vorher angelegte Show-DB war danach gar nicht
            # mehr ladbar. Der Fehler steht drei Zeilen weiter oben als Notiz;
            # eine Notiz allein hat ihn nicht verhindert, ein Test tut es
            # (tests/test_show_db_migration_coverage.py prueft strukturell,
            # dass JEDE Modell-Spalte migriert wird).
            if pcols and "element_rotation" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN element_rotation "
                    "INTEGER DEFAULT 0"))
            if pcols and "element_flip" not in pcols:
                conn.execute(text(
                    "ALTER TABLE patched_fixtures ADD COLUMN element_flip "
                    "BOOLEAN DEFAULT 0"))
    except Exception as e:
        print(f"[models] migrate_show_db error: {e}")


def migrate_fixtures_db(engine) -> None:
    """Idempotente Migration fuer die Fixture-DB (fixtures.db): ergaenzt die
    Spalte ``channel_ranges.kind`` (M1.2), falls eine aeltere DB sie noch nicht
    hat. create_all() legt nur fehlende Tabellen an, keine fehlenden Spalten."""
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(channel_ranges)"))}
            if cols and "kind" not in cols:
                conn.execute(text(
                    "ALTER TABLE channel_ranges ADD COLUMN kind VARCHAR DEFAULT ''"))
            # FM-12: expliziter 3D-Modell-Override am Profil ("" = Automatik).
            fcols = {row[1] for row in conn.execute(text("PRAGMA table_info(fixtures)"))}
            if fcols and "viz_model" not in fcols:
                conn.execute(text(
                    "ALTER TABLE fixtures ADD COLUMN viz_model VARCHAR(40) DEFAULT ''"))
            # VIZ-50a: physische Rasterform eines Pixel-Panels (0 = nicht
            # hinterlegt -> der Renderer raet wie bisher). Dieselbe Falle wie bei
            # `pixel_order` (PR #514): ohne ALTER TABLE waere jede bestehende
            # fixtures.db unbrauchbar, weil das ORM alle Modell-Spalten abfragt
            # ("no such column: fixture_modes.grid_rows") — und die Bibliothek
            # ist die eine Datei, die der Nutzer nicht mal eben neu anlegt.
            # CDX-52: dazu die Rasterform der eigenen Weiss-Segmente
            # (white_rows/white_cols) — dieselbe Falle, dieselbe Behandlung.
            mcols = {row[1] for row in conn.execute(text("PRAGMA table_info(fixture_modes)"))}
            for _gcol in ("grid_rows", "grid_cols", "white_rows", "white_cols"):
                if mcols and _gcol not in mcols:
                    conn.execute(text(
                        f"ALTER TABLE fixture_modes ADD COLUMN {_gcol} INTEGER DEFAULT 0"))
    except Exception as e:
        print(f"[models] migrate_fixtures_db error: {e}")


def create_all_idempotent(engine) -> None:
    """``Base.metadata.create_all``, aber tolerant gegen ein bereits vorhandenes
    Schema (QA-06).

    ``create_all(checkfirst=True)`` reflektiert vor jedem ``CREATE`` das
    ``sqlite_master``. Greifen zwei Verbindungen/Laeufe auf dieselbe SQLite-Datei
    zu (z. B. eine frisch neu aufgebaute Engine, waehrend eine alte ihre
    Verbindung noch haelt, oder ein paralleler Lauf), liegt zwischen Reflexion
    und ``CREATE`` ein Zeitfenster (TOCTOU): die Reflexion sieht die Tabelle noch
    nicht, der eigene ``CREATE`` kollidiert dann mit ``table ... already exists``.
    Die Tabellen sind in diesem Fall bereits da -> der Fehler ist harmlos und
    wird geschluckt. Jeder andere ``OperationalError`` (z. B. ``disk I/O``)
    fliegt unveraendert weiter."""
    from sqlalchemy.exc import OperationalError
    try:
        Base.metadata.create_all(engine)
    except OperationalError as e:
        if "already exists" not in str(e).lower():
            raise


def create_db(path: str):
    engine = create_engine(f"sqlite:///{path}", echo=False)
    create_all_idempotent(engine)
    migrate_show_db(engine)
    return engine
