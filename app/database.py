"""Configuration SQLite et session SQLAlchemy."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_DB_PATH = BASE_DIR / "stratys.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Générateur de session DB pour les routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
