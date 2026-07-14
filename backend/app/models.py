"""
SQLite for now (Stage I's own plan doc: single-writer sync API is exactly
SQLite's territory, SQLAlchemy makes a future Postgres swap a connection-
string change, not a rewrite). `blob` mirrors game/save.py's state dict
verbatim (json.dumps of it) rather than being decomposed into columns - the
whole point of that dict already being one coherent versioned/migrated JSON
document (see docs/save-schema.md) is that the server doesn't need to know
its internal shape at all, just store and return it. Merge logic lives
client-side (Stage I5's merge_states() in game/save.py); this server is a
dumb last-write-wins store on purpose.
"""
from pathlib import Path

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_DB_PATH = Path(__file__).resolve().parent.parent / "dungeon_quest.db"
engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    google_sub = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)


class SaveRow(Base):
    __tablename__ = "save_rows"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    blob = Column(Text, nullable=False)
    updated_at = Column(Float, nullable=False)


class BalanceConfig(Base):
    """Stage I4: admin-panel overrides on top of the game's own balance
    defaults (game/items.py, game/difficulty.py, game/spells.py,
    game/stats.py). Absent key = code default stands - this table only
    ever holds the curated subset an admin actually changed, never a full
    mirror of every constant."""
    __tablename__ = "balance_config"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(Float, nullable=False)


class AppearanceOverride(Base):
    """Stage K18: pixel-art overrides from the admin panel's canvas editor -
    one row per entity key ("monster.goblin", "item.potion_orange", ...),
    data_url holding a full "data:image/png;base64,..." string straight
    from the browser canvas's toDataURL(). Same "absent key = code default
    (the procedural painter) stands" shape as BalanceConfig above - this
    table never mirrors every sprite, only the ones an admin actually
    repainted."""
    __tablename__ = "appearance_overrides"

    key = Column(String, primary_key=True)
    data_url = Column(Text, nullable=False)
    updated_at = Column(Float, nullable=False)


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
