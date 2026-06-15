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
    except Exception as e:
        print(f"[models] migrate_fixtures_db error: {e}")


def create_db(path: str):
    engine = create_engine(f"sqlite:///{path}", echo=False)
    Base.metadata.create_all(engine)
    migrate_show_db(engine)
    return engine
