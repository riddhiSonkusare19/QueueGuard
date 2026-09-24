import datetime
import uuid

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    total_slots = Column(Integer, nullable=False)


class Slot(Base):
    __tablename__ = "slots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="available")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    slot_id = Column(String, nullable=True)
    user_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


def make_engine(database_url: str | None = None):
    return create_engine(
        database_url or settings.DATABASE_URL,
        pool_pre_ping=True,
    )


def make_session_factory(engine):
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )


engine = make_engine()
SessionLocal = make_session_factory(engine)


def init_db(engine_=None):
    """Creates tables if they don't exist.

    Called on app startup; also useful for tests against
    an in-memory SQLite database.
    """
    Base.metadata.create_all(bind=engine_ or engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()