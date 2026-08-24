import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, OpportunityRecord, OrganizationRecord, set_tenant_context
from app.strategy import StrategyUpsert, StrategyVersionConflict, get_strategy, save_strategy


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title="并发控制测试项目",
        country="测试国",
        region="测试区域",
        sector="公路工程",
        stage="测试阶段",
        owner="测试业主",
        estimated_value_usd_m=None,
        summary="测试策略并发控制。",
        score=70,
        grade="B",
        confidence=70,
        decision="WATCH",
        breakdown={
            "strategic_fit": 15,
            "project_maturity": 10,
            "financing": 10,
            "client_quality": 8,
            "capability_fit": 12,
            "local_position": 5,
            "competition": 6,
            "risk_control": 4,
        },
        pursuit_thesis="测试赢标主张",
        next_actions=[],
        is_demo=False,
    )


def test_strategy_version_increments_and_stale_write_is_rejected() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = OrganizationRecord(
            id=str(uuid.uuid4()),
            name=f"Strategy Org {uuid.uuid4().hex[:6]}",
            code=f"STR-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(org)
        session.flush()
        opportunity_id = f"strategy-{uuid.uuid4().hex[:8]}"
        session.add(_opportunity(opportunity_id, org.id))
        session.commit()
        set_tenant_context(session, org.id)

        initial = get_strategy(opportunity_id, session)
        assert initial.version == 0
        assert initial.etag == '"strategy-0"'

        first = save_strategy(
            opportunity_id,
            StrategyUpsert(
                expected_version=0,
                win_theme="第一版赢标主张",
                client_need="降低接口风险",
            ),
            session,
        )
        assert first.version == 1
        assert first.strategy["win_theme"] == "第一版赢标主张"

        with pytest.raises(StrategyVersionConflict) as exc:
            save_strategy(
                opportunity_id,
                StrategyUpsert(
                    expected_version=0,
                    win_theme="基于旧版本的覆盖写入",
                ),
                session,
            )
        assert exc.value.expected_version == 0
        assert exc.value.current_version == 1

        latest = get_strategy(opportunity_id, session)
        assert latest.version == 1
        assert latest.strategy["win_theme"] == "第一版赢标主张"
