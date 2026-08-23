from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base, OpportunityRecord, OrganizationRecord, PursuitActionRecord, WatchItemRecord
from app.seed import HERO_ID, reset_demo_data, seed_demo_data


def test_reset_demo_is_repeatable_and_preserves_non_demo() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        org = OrganizationRecord(
            id=str(uuid4()),
            name="测试组织",
            code="TEST-ORG",
            is_active=True,
        )
        session.add(org)
        session.flush()

        session.add(
            OpportunityRecord(
                id="public-real-opportunity",
                organization_id=org.id,
                title="公开项目样例",
                country="测试国",
                region="测试区域",
                sector="港口工程",
                stage="公开信息阶段",
                owner="公开业主",
                estimated_value_usd_m=None,
                summary="非 Demo 数据必须被保留。",
                score=50,
                grade="C",
                confidence=60,
                decision="CAUTION",
                breakdown={
                    "strategic_fit": 10,
                    "project_maturity": 8,
                    "financing": 6,
                    "client_quality": 6,
                    "capability_fit": 10,
                    "local_position": 4,
                    "competition": 4,
                    "risk_control": 2,
                },
                pursuit_thesis="用于验证 reset-demo 安全边界。",
                next_actions=[],
                is_demo=False,
            )
        )
        session.commit()

        assert seed_demo_data(session) >= 1
        hero = session.get(OpportunityRecord, HERO_ID)
        assert hero is not None
        assert hero.score == 72
        assert hero.grade == "B"
        assert session.scalar(select(WatchItemRecord).where(WatchItemRecord.opportunity_id == HERO_ID)) is not None
        assert len(session.scalars(select(PursuitActionRecord).where(PursuitActionRecord.opportunity_id == HERO_ID)).all()) == 3

        # Simulate a prior demo run changing the hero state.
        hero.score = 81
        hero.grade = "A"
        session.commit()

        removed = reset_demo_data(session)
        assert removed >= 1
        assert session.get(OpportunityRecord, "public-real-opportunity") is not None
        assert session.get(OpportunityRecord, HERO_ID) is None

        assert seed_demo_data(session) >= 1
        hero = session.get(OpportunityRecord, HERO_ID)
        assert hero is not None
        assert hero.score == 72
        assert hero.grade == "B"
        assert len(session.scalars(select(PursuitActionRecord).where(PursuitActionRecord.opportunity_id == HERO_ID)).all()) == 3
