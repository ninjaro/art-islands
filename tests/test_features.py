from __future__ import annotations

import json
import pathlib

from art_islands import features
from art_islands.model import DEFAULT_SETTINGS

SETTINGS = DEFAULT_SETTINGS["features"]


def make_features(
    concepts=(),
    contributors=(),
    advisories=(),
):
    return features.extract_features(concepts, contributors, advisories, SETTINGS)


def test_contributor_features_use_role_multipliers() -> None:
    extracted = make_features(
        concepts=[(1, "Cyberpunk", "Genre", 80, 0)],
        contributors=[(50, "R. Scott", "person", "director", 80, 0)],
    )
    assert abs(extracted["concept:1"].value - 0.8) < 1e-12
    assert abs(extracted["entity:50"].value - 0.8 * 0.5) < 1e-12
    assert extracted["entity:50"].source == "contributor"
    assert extracted["entity:50"].relation_type == "director"


def test_strongest_role_wins_for_repeated_entity() -> None:
    extracted = make_features(
        contributors=[
            (50, "Person", "person", "cast_member", 80, 0),
            (50, "Person", "person", "director", 80, 0),
        ]
    )
    assert list(extracted) == ["entity:50"]
    assert extracted["entity:50"].relation_type == "director"


def test_unmapped_roles_are_skipped() -> None:
    assert make_features(contributors=[(50, "Person", "person", "main_subject", 80, 0)]) == {}


def test_organization_targets_get_organization_source() -> None:
    extracted = make_features(contributors=[(60, "Studio", "organization", "production_company", 40, 0)])
    assert extracted["entity:60"].source == "organization"
    assert abs(extracted["entity:60"].value - 0.4 * 0.2) < 1e-12


def test_advisories_become_content_guide_features() -> None:
    extracted = make_features(advisories=[(7, "Violence", 72), (8, "Other", None)])
    assert list(extracted) == ["advisory:7"]
    assert abs(extracted["advisory:7"].value - 0.72 * 0.25) < 1e-12
    assert extracted["advisory:7"].source == "content-guide"


def test_negative_polarity_flips_sign() -> None:
    extracted = make_features(concepts=[(1, "Dreams", "Theme", 60, -1)])
    assert abs(extracted["concept:1"].value + 0.6) < 1e-12


def test_null_concept_weights_are_uncalibrated_and_skipped() -> None:
    extracted = make_features(concepts=[(1, "Pending", "Theme", None, 0), (2, "Ready", "Theme", 60, 0)])
    assert list(extracted) == ["concept:2"]


def _index(work_specs):
    base = {
        work_id: make_features(**spec)
        for work_id, spec in work_specs.items()
    }
    return features.build_feature_index(base)


def test_higher_weight_raises_similarity() -> None:
    index = _index(
        {
            1: {"concepts": [(1, "A", "Genre", 90, 0), (2, "B", "Genre", 50, 0)]},
            2: {"concepts": [(1, "A", "Genre", 90, 0), (3, "C", "Genre", 50, 0)]},
            3: {"concepts": [(1, "A", "Genre", 30, 0), (3, "C", "Genre", 50, 0)]},
        }
    )
    strong, _, _ = features.similarity_between(index, 1, 2)
    weak, _, _ = features.similarity_between(index, 1, 3)
    assert strong > weak > 0


def test_opposite_polarity_decreases_compatibility() -> None:
    index = _index(
        {
            1: {"concepts": [(1, "A", "Genre", 80, 0), (2, "B", "Genre", 60, 0)]},
            2: {"concepts": [(1, "A", "Genre", 80, 0), (2, "B", "Genre", 60, 0)]},
            3: {"concepts": [(1, "A", "Genre", 80, 0), (2, "B", "Genre", 60, -1)]},
        }
    )
    aligned, _, _ = features.similarity_between(index, 1, 2)
    opposed, _, _ = features.similarity_between(index, 1, 3)
    assert opposed < aligned


def test_generic_concepts_contribute_less_than_rare_ones() -> None:
    generic = (1, "Generic", "Genre", 80, 0)
    index = _index(
        {
            1: {"concepts": [generic, (2, "Rare", "Genre", 80, 0)]},
            2: {"concepts": [generic, (2, "Rare", "Genre", 80, 0)]},
            3: {"concepts": [generic, (3, "Other", "Genre", 80, 0)]},
            4: {"concepts": [generic, (3, "Other", "Genre", 80, 0)]},
            5: {"concepts": [generic]},
            6: {"concepts": [generic]},
        }
    )
    via_rare, _, factors = features.similarity_between(index, 1, 2)
    via_generic, _, _ = features.similarity_between(index, 1, 5)
    assert via_rare > via_generic
    assert factors[0]["id"] == "concept:2"


def test_similarity_reports_shared_count_and_labeled_factors() -> None:
    index = _index(
        {
            1: {
                "concepts": [(1, "Cyberpunk", "Genre", 90, 0)],
                "contributors": [(50, "R. Scott", "person", "director", 80, 0)],
            },
            2: {
                "concepts": [(1, "Cyberpunk", "Genre", 70, 0)],
                "contributors": [(50, "R. Scott", "person", "director", 80, 0)],
            },
            3: {"concepts": [(9, "Other", "Genre", 50, 0)]},
        }
    )
    similarity, shared, factors = features.similarity_between(index, 1, 2)
    assert similarity > 0
    assert shared == 2
    labels = {factor["label"] for factor in factors}
    assert "Cyberpunk" in labels and "R. Scott" in labels


def test_determinism() -> None:
    spec = {
        1: {"concepts": [(1, "A", "Genre", 80, 0), (2, "B", "Genre", 40, -1)]},
        2: {"concepts": [(1, "A", "Genre", 70, 0), (2, "B", "Genre", 20, 0)]},
    }
    assert features.similarity_between(_index(spec), 1, 2) == features.similarity_between(_index(spec), 1, 2)


def test_golden_fixture_is_current() -> None:
    from tools.generate_feature_golden import build_golden

    path = pathlib.Path(__file__).resolve().parents[1] / "shared" / "fixtures" / "feature-golden.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert build_golden() == stored, (
        "shared/fixtures/feature-golden.json is stale; regenerate with "
        "`python tools/generate_feature_golden.py` if the semantics change was intentional"
    )
