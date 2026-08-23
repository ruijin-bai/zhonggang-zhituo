import argparse

from sqlalchemy import func, select

from .db import Base, OpportunityRecord, SessionLocal, engine
from .seed import seed_demo_data


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        created = seed_demo_data(session)
    print(f"database ready; seeded {created} demo opportunities")


def seed() -> None:
    with SessionLocal() as session:
        created = seed_demo_data(session)
    print(f"seeded {created} demo opportunities")


def status() -> None:
    with SessionLocal() as session:
        count = session.scalar(select(func.count()).select_from(OpportunityRecord)) or 0
    print(f"opportunities={count}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="zhituo-api")
    parser.add_argument("command", choices=["init-db", "seed", "status"])
    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "seed":
        seed()
    else:
        status()


if __name__ == "__main__":
    main()
