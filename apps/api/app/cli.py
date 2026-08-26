import argparse
import os

from sqlalchemy import func, select

from .db import Base, OpportunityRecord, SessionLocal, engine
from .pilot_bootstrap import ensure_pilot_identity
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


def bootstrap_pilot() -> None:
    required = {
        "PILOT_ADMIN_EMAIL": os.getenv("PILOT_ADMIN_EMAIL", ""),
        "PILOT_ORGANIZATION_NAME": os.getenv("PILOT_ORGANIZATION_NAME", ""),
        "PILOT_ORGANIZATION_CODE": os.getenv("PILOT_ORGANIZATION_CODE", ""),
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise SystemExit(f"missing required pilot identity settings: {', '.join(missing)}")

    with SessionLocal() as session:
        organization, user, membership = ensure_pilot_identity(
            session,
            email=required["PILOT_ADMIN_EMAIL"],
            display_name=os.getenv("PILOT_ADMIN_DISPLAY_NAME", "Pilot Administrator"),
            organization_name=required["PILOT_ORGANIZATION_NAME"],
            organization_code=required["PILOT_ORGANIZATION_CODE"],
        )
        summary = (organization.code, user.email, membership.role)
    print(
        "pilot identity ready; "
        f"organization={summary[0]}; user={summary[1]}; role={summary[2]}; demo_data=0"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="zhituo-api")
    parser.add_argument(
        "command",
        choices=["init-db", "seed", "reset-demo", "status", "bootstrap-pilot"],
    )
    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "seed":
        seed()
    elif args.command == "reset-demo":
        reset_demo()
    elif args.command == "status":
        status()
    else:
        bootstrap_pilot()


if __name__ == "__main__":
    main()
