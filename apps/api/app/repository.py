import json
from functools import lru_cache
from pathlib import Path
from .models import Opportunity

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "demo" / "opportunities.json"

@lru_cache(maxsize=1)
def load_opportunities() -> list[Opportunity]:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [Opportunity.model_validate(item) for item in payload]


def get_opportunity(opportunity_id: str) -> Opportunity | None:
    return next((item for item in load_opportunities() if item.id == opportunity_id), None)
