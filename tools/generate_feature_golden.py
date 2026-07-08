"""Regenerate shared/fixtures/feature-golden.json from the Python reference
implementation of the shared feature model (docs/feature-model.md).

TypeScript (web/src/lib/features.golden.test.ts) must reproduce these numbers
within 1e-9; tests/test_features.py fails when this file drifts from the
implementation, so regenerating is always an explicit, reviewed act:

    python tools/generate_feature_golden.py
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from art_islands import features  # noqa: E402
from art_islands.model import DEFAULT_SETTINGS  # noqa: E402

SETTINGS = DEFAULT_SETTINGS["features"]

# Coverage: positive/negative polarity, weights 30-90, one generic concept on
# every work vs rare pair-only concepts, shared director, conflicting
# contributor evidence (same entity, opposite polarity), content-guide
# similarity, cross-family works, dated and undated works.
WORKS = [
    {
        "id": 1,
        "date": "1982-06-25",
        "kind": "film",
        "concepts": [
            {"id": 10, "label": "Cyberpunk", "category": "Genre", "weight": 90, "polarity": 0},
            {"id": 11, "label": "Neo-noir", "category": "Style", "weight": 60, "polarity": 0},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 50, "label": "R. Scott", "family": "person", "role": "director", "weight": 80, "polarity": 0},
            {"entityId": 60, "label": "Big Studio", "family": "organization", "role": "production_company", "weight": 40, "polarity": 0},
        ],
        "advisories": [{"categoryId": 1, "label": "Violence", "intensity": 72}],
    },
    {
        "id": 2,
        "date": "1995-03-31",
        "kind": "film",
        "concepts": [
            {"id": 10, "label": "Cyberpunk", "category": "Genre", "weight": 70, "polarity": 0},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 50, "label": "R. Scott", "family": "person", "role": "director", "weight": 80, "polarity": 0},
        ],
        "advisories": [{"categoryId": 1, "label": "Violence", "intensity": 68}],
    },
    {
        "id": 3,
        "date": "1979-11-30",
        "kind": "music",
        "concepts": [
            {"id": 20, "label": "Progressive rock", "category": "Genre", "weight": 90, "polarity": 0},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 70, "label": "The Band", "family": "group", "role": "music_artist", "weight": 90, "polarity": 0},
        ],
        "advisories": [{"categoryId": 2, "label": "Sensory disorientation", "intensity": 64}],
    },
    {
        "id": 4,
        "date": "1981-02-13",
        "kind": "music",
        "concepts": [
            {"id": 20, "label": "Progressive rock", "category": "Genre", "weight": 60, "polarity": 0},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 70, "label": "The Band", "family": "group", "role": "music_artist", "weight": 90, "polarity": 0},
        ],
        "advisories": [{"categoryId": 2, "label": "Sensory disorientation", "intensity": 40}],
    },
    {
        "id": 5,
        "date": "2001-09-14",
        "kind": "film",
        "concepts": [
            {"id": 30, "label": "Romance", "category": "Genre", "weight": 60, "polarity": -1},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 80, "label": "A. Performer", "family": "person", "role": "cast_member", "weight": 40, "polarity": 0},
        ],
        "advisories": [],
    },
    {
        "id": 6,
        "date": "2001-10-26",
        "kind": "film",
        "concepts": [
            {"id": 30, "label": "Romance", "category": "Genre", "weight": 60, "polarity": 0},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 80, "label": "A. Performer", "family": "person", "role": "cast_member", "weight": 40, "polarity": 0},
        ],
        "advisories": [],
    },
    {
        "id": 7,
        "date": None,
        "kind": "work",
        "concepts": [{"id": 40, "label": "Marginalia", "category": "Subject", "weight": 30, "polarity": 0}],
        "contributors": [],
        "advisories": [],
    },
    {
        "id": 8,
        "date": "1990-05-01",
        "kind": "film",
        "concepts": [
            {"id": 10, "label": "Cyberpunk", "category": "Genre", "weight": 30, "polarity": 0},
            {"id": 99, "label": "English", "category": "Language", "weight": 80, "polarity": 0},
        ],
        "contributors": [
            {"entityId": 50, "label": "R. Scott", "family": "person", "role": "producer", "weight": 50, "polarity": 0},
            {"entityId": 70, "label": "The Band", "family": "group", "role": "music_artist", "weight": 60, "polarity": -1},
        ],
        "advisories": [{"categoryId": 1, "label": "Violence", "intensity": 80}],
    },
]


def base_features_for(work: dict) -> dict[str, features.Feature]:
    return features.extract_features(
        [(c["id"], c["label"], c["category"], c["weight"], c["polarity"]) for c in work["concepts"]],
        [
            (c["entityId"], c["label"], c["family"], c["role"], c["weight"], c["polarity"])
            for c in sorted(work["contributors"], key=lambda entry: entry["role"])
        ],
        [(a["categoryId"], a["label"], a["intensity"]) for a in work["advisories"]],
        SETTINGS,
    )


def build_golden() -> dict:
    base = {work["id"]: base_features_for(work) for work in WORKS}
    index = features.build_feature_index(base)

    expected_features = {
        str(work_id): {key: feature.value for key, feature in index.features_by_id[work_id].items()}
        for work_id in sorted(base)
    }
    similarities = []
    for a, b in combinations(sorted(base), 2):
        similarity, shared, top_factors = features.similarity_between(index, a, b)
        similarities.append(
            {
                "a": a,
                "b": b,
                "similarity": similarity,
                "sharedFeatureCount": shared,
                "topFactors": top_factors,
            }
        )
    return {
        "note": "Generated by tools/generate_feature_golden.py; do not edit by hand.",
        "settings": dict(SETTINGS),
        "works": WORKS,
        "expected": {"features": expected_features, "similarities": similarities},
    }


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "shared" / "fixtures" / "feature-golden.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_golden(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
