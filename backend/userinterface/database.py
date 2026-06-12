import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

db_dir = os.path.join(os.path.dirname(__file__), "db")
os.makedirs(db_dir, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(db_dir, 'cms.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
    finally:
        cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models import CameraFeature  # noqa: F401

    Base.metadata.create_all(bind=engine)


def test_database_connection():
    try:
        with engine.connect():
            return True
    except SQLAlchemyError:
        return False
