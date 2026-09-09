import argparse
import os

from sqlalchemy import func, select

from .db import Base, OpportunityRecord, SessionLocal, engine
from .pilot_bootstrap import ensure_pilot_identity
from .seed import reset_demo_data, seed_demo_data

# Business models are declared per feature module. SQLAlchemy only registers a table once its
# module has been imported, so schema creation must import every module that owns a model —
# otherwise create_all() silently builds a partial database.
_MODEL_MODULES = (
    "candidate_db",
    "intelligence_db",
    "opportunity_evidence_db",
    "pursuit_db",
    "pursuit_delivery_db",
    "pursuit_reminder_db",
    "source_db",
)


def _import_all_models() -> None:
    import importlib

    for module_name in _MODEL_MODULES:
        importlib.import_module(f".{module_name}", package=__package__)


def _stamp_alembic_head() -> None:
    """Mark the ORM-created schema as current so a later `alembic upgrade` is not confused.

    Only relevant for SQLite demo databases, which are built with create_all() instead of
    migrations (SQLite cannot ALTER constraints). Never touches PostgreSQL, where migrations
    remain the single source of truth.
    """
    try:
        from alembic.config import Config

        from alembic import command

        ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")
        command.stamp(Config(ini_path), "head")
    except Exception as error:  # pragma: no cover - best effort, never block startup
        print(f"alembic stamp skipped: {error}")


def init_db() -> None:
    _import_all_models()
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _stamp_alembic_head()
    with SessionLocal() as session:
        created = seed_demo_data(session)
    print(f"database ready ({engine.dialect.name}); seeded {created} demo opportunities")


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
