import json
from importlib.resources import files
from pathlib import Path


def test_packaged_demo_seed_matches_repository_fixture() -> None:
    packaged = json.loads(files("app").joinpath("demo_data/opportunities.json").read_text(encoding="utf-8"))
    repository_fixture = Path(__file__).resolve().parents[3] / "data" / "demo" / "opportunities.json"
    expected = json.loads(repository_fixture.read_text(encoding="utf-8"))

    assert packaged == expected
    assert {item["id"] for item in packaged} >= {"west-africa-port-access-corridor"}
