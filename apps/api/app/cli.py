import argparse

from sqlalchemy import func, select

from .db import Base, OpportunityRecord, SessionLocal, engine
from .seed import reset_demo_data, seed_demo_data


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        created = seed_demo_data(session)
    print(f"database ready; seeded {created} demo opportunities")


def seed() -> None:
    with SessionLocal() as session:
        created = seed_demo_data(session)
    print(f"seeded {created} demo opportunities")


def reset_demo() -> None:
    with SessionLocal() as session:
        removed = reset_demo_data(session)
        created = seed_demo_data(session)
    print(f"demo reset complete; removed {removed}, seeded {created} demo opportunities")


def status() -> None:
    with SessionLocal() as session:
        count = session.scalar(select(func.count()).select_from(OpportunityRecord)) or 0
        demo_count = session.scalar(
            select(func.count()).select_from(OpportunityRecord).where(OpportunityRecord.is_demo.is_(True))
        ) or 0
    print(f"opportunities={count}; demo_opportunities={demo_count}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="zhituo-api")
    parser.add_argument("command", choices=["init-db", "seed", "reset-demo", "status"])
    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "seed":
        seed()
    elif args.command == "reset-demo":
        reset_demo()
    else:
        status()


if __name__ == "__main__":
    main()
