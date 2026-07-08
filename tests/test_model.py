from __future__ import annotations

from art_islands import model
from art_islands.model import (
    parse_wikidata_date,
)


def test_wikidata_date_parsing() -> None:
    assert parse_wikidata_date(
        {"time": "+1977-00-00T00:00:00Z", "precision": 9}
    ) == ("1977-01-01", 1)
    assert parse_wikidata_date(
        {"time": "+1977-05-00T00:00:00Z", "precision": 10}
    ) == ("1977-05-01", 2)
    assert parse_wikidata_date(
        {"time": "+1977-05-22T00:00:00Z", "precision": 11}
    ) == ("1977-05-22", 3)


def test_settings_defaults_include_new_sections() -> None:
    settings = model.settings_with_defaults({})
    assert settings["features"]["directorMultiplier"] == 0.5
    assert settings["browse"]["pageSizeOptions"] == [25, 50, 100]
    assert settings["browse"]["defaultPageSize"] == 50
    assert settings["evolution"]["kindMismatchFactor"] == 0.6
    assert settings["islands"]["maxInferredNeighborsPerNode"] == 8


def test_settings_legacy_aliases() -> None:
    settings = model.settings_with_defaults(
        {"islands": {"maxNeighborsPerSeed": 12}, "evolution": {"minimumSharedTags": 3}}
    )
    assert settings["islands"]["maxInferredNeighborsPerNode"] == 12
    assert "maxNeighborsPerSeed" not in settings["islands"]
    assert settings["evolution"]["minimumSharedFeatures"] == 3


def test_settings_page_size_validation() -> None:
    settings = model.settings_with_defaults(
        {"browse": {"defaultPageSize": 37, "pageSizeOptions": ["a", 10]}}
    )
    assert settings["browse"]["pageSizeOptions"] == [25, 50, 100]
    assert settings["browse"]["defaultPageSize"] == 50
