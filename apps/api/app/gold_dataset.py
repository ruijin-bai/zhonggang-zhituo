from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

REQUIRED_POSITIVE_FIELDS = (
    "sample_id",
    "source_name",
    "source_url",
    "published_at",
    "country",
    "sector",
    "stage",
    "title",
    "owner",
    "financing",
    "procurement_signal",
    "gold_evidence",
    "must_not_infer",
)


@dataclass(frozen=True)
class GoldDatasetValidation:
    samples: int
    positives: int
    negatives: int
    countries: int
    sectors: int
    evidence_items: int
    forbidden_claim_items: int


def project_expected(sample: dict) -> bool:
    return bool(sample.get("project_expected", True))


def safety_constraints(sample: dict) -> dict:
    """Return structured anti-hallucination rules for evaluation.

    The public Gold set currently contains pre-award / project-information sources. Unless a
    sample explicitly opts out, competitor/partner identities and unsupported monetary values
    are forbidden. This is intentionally conservative: unknown is preferable to fabrication.
    """

    configured = sample.get("safety_constraints") or {}
    return {
        "forbidden_party_roles": list(
            configured.get("forbidden_party_roles", ["competitor", "partner"])
        ),
        "forbidden_non_null_fields": list(
            configured.get("forbidden_non_null_fields", ["estimated_value_usd_m"])
        ),
    }


def normalize_source_url(url: str) -> str:
    """Normalize a source URL for duplicate detection without changing its resource identity."""

    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def is_known_aggregate_listing(url: str) -> bool:
    """Reject known listing/search pages that mix many projects into one Gold input.

    AfDB's individual document pages live directly under ``/<lang>/documents/<slug>`` or are
    direct files under ``/sites/...``. Paths under ``documents/project-related-procurement``
    are category/listing pages and are unsuitable as one-sample-one-source Gold evidence.
    """

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower().rstrip("/")
    return host.endswith("afdb.org") and "/documents/project-related-procurement" in path


def load_gold_dataset(
    repository_root: Path,
    *,
    include_extensions: bool = True,
    include_regression_negatives: bool = False,
) -> list[dict]:
    """Load the versioned Gold corpus in deterministic order.

    Extension files are part of the real-source Gold corpus. Synthetic negative fixtures are
    opt-in and only belong in engineering regression runs; they must never make a report
    publishable as a real-world accuracy claim.
    """

    benchmark_dir = repository_root / "data" / "benchmark"
    paths = [benchmark_dir / "gold_dataset.json"]
    if include_extensions:
        paths.extend(sorted(benchmark_dir.glob("gold_dataset_extension*.json")))
    if include_regression_negatives:
        paths.append(benchmark_dir / "regression_negatives.json")

    samples: list[dict] = []
    for path in paths:
        if not path.exists():
            if path.name == "regression_negatives.json":
                continue
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Gold Dataset file must contain a JSON array: {path}")
        samples.extend(payload)
    return samples


def validate_gold_dataset(samples: list[dict], *, minimum_samples: int = 10) -> GoldDatasetValidation:
    errors: list[str] = []
    if len(samples) < minimum_samples:
        errors.append(f"dataset requires at least {minimum_samples} samples; found {len(samples)}")

    ids = [str(sample.get("sample_id") or "").strip() for sample in samples]
    duplicates = sorted(sample_id for sample_id, count in Counter(ids).items() if sample_id and count > 1)
    if duplicates:
        errors.append(f"duplicate sample_id values: {', '.join(duplicates)}")

    positive_urls = [
        normalize_source_url(str(sample.get("source_url") or ""))
        for sample in samples
        if project_expected(sample) and str(sample.get("source_url") or "").strip()
    ]
    duplicate_urls = sorted(url for url, count in Counter(positive_urls).items() if count > 1)
    if duplicate_urls:
        errors.append(f"duplicate positive source_url values: {', '.join(duplicate_urls)}")

    positives = 0
    negatives = 0
    countries: set[str] = set()
    sectors: set[str] = set()
    evidence_items = 0
    forbidden_items = 0

    for index, sample in enumerate(samples):
        sample_id = ids[index] or f"row-{index + 1}"
        expected = project_expected(sample)
        positives += int(expected)
        negatives += int(not expected)

        if expected:
            missing = [field for field in REQUIRED_POSITIVE_FIELDS if field not in sample]
            if missing:
                errors.append(f"{sample_id}: missing fields: {', '.join(missing)}")

        url = str(sample.get("source_url") or "").strip()
        if expected:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{sample_id}: source_url must be an absolute HTTPS URL")
            if is_known_aggregate_listing(url):
                errors.append(f"{sample_id}: source_url must identify one document, not an aggregate listing")

        evidence = sample.get("gold_evidence") or []
        forbidden = sample.get("must_not_infer") or []
        if expected and (not isinstance(evidence, list) or not evidence):
            errors.append(f"{sample_id}: gold_evidence must contain at least one item")
        if expected and (not isinstance(forbidden, list) or not forbidden):
            errors.append(f"{sample_id}: must_not_infer must contain at least one item")
        if isinstance(evidence, list):
            evidence_items += len(evidence)
        if isinstance(forbidden, list):
            forbidden_items += len(forbidden)

        if not expected:
            fixture_text = str(sample.get("fixture_text") or "").strip()
            if not fixture_text:
                errors.append(f"{sample_id}: regression negative requires fixture_text")
            if sample.get("source_url"):
                errors.append(f"{sample_id}: synthetic regression negative must not claim source_url")

        country = str(sample.get("country") or "").strip()
        sector = str(sample.get("sector") or "").strip()
        if country:
            countries.add(country)
        if sector:
            sectors.add(sector)

        constraints = safety_constraints(sample)
        allowed_roles = {"owner", "financier", "competitor", "partner"}
        bad_roles = set(constraints["forbidden_party_roles"]) - allowed_roles
        if bad_roles:
            errors.append(f"{sample_id}: unknown forbidden party roles: {sorted(bad_roles)}")

    if not positives:
        errors.append("dataset must contain positive project samples")

    if errors:
        raise ValueError("Invalid Gold Dataset:\n- " + "\n- ".join(errors))

    return GoldDatasetValidation(
        samples=len(samples),
        positives=positives,
        negatives=negatives,
        countries=len(countries),
        sectors=len(sectors),
        evidence_items=evidence_items,
        forbidden_claim_items=forbidden_items,
    )
