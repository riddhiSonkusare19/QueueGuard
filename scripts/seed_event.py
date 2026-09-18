"""Seeds a demo event directly into Postgres so there's something to
book against. Run against the booking_service's dependencies:

    DATABASE_URL=postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard \\
        python scripts/seed_event.py concert-1 "Test Concert" 20
"""

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "booking_service"))

from app.db import Base, Event  # noqa: E402


def main():
    event_id = sys.argv[1] if len(sys.argv) > 1 else "concert-1"
    name = sys.argv[2] if len(sys.argv) > 2 else "Demo Event"
    slots = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    database_url = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard"
    )
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    session.merge(Event(id=event_id, name=name, total_slots=slots))
    session.commit()
    session.close()

    print(f"seeded event '{event_id}' ({name}) with {slots} slots")


if __name__ == "__main__":
    main()
