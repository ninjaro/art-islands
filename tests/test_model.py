from __future__ import annotations

import json
import sqlite3

from art_islands import model
from art_islands.model import (
    ENTITY_KIND_FILM,
    LINK_KIND_ADAPTED_FROM,
    LINK_KIND_ASSOCIATED,
    LINK_KIND_INFLUENCED_BY,
    SourceData,
    SourcePair,
    SourceTag,
    TAG_KIND_LEGACY_RELATION_TEXT,
    TAG_KIND_NAMESPACED,
    export_static_data,
    migrate_art_database,
    parse_tag_name,
    parse_wikidata_date,
)


def write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_tag_and_date_parsing() -> None:
    parsed = parse_tag_name("genre:adult_horror")
    assert parsed.tag_kind == TAG_KIND_NAMESPACED
    assert parsed.namespace == "genre"
    assert parsed.value == "adult_horror"

    parsed = parse_tag_name("narration:host:direct_address")
    assert parsed.namespace == "narration"
    assert parsed.value == "host:direct_address"

    parsed = parse_tag_name("influence_person__Q905__surreal_dream_logic")
    assert parsed.tag_kind == TAG_KIND_LEGACY_RELATION_TEXT
    assert parsed.target_qid == "Q905"
    assert parsed.link_kind == LINK_KIND_INFLUENCED_BY

    parsed = parse_tag_name("influence_artist__elvis_presley")
    assert parsed.tag_kind == TAG_KIND_LEGACY_RELATION_TEXT
    assert parsed.target_qid is None

    assert parse_wikidata_date(
        {"time": "+1977-00-00T00:00:00Z", "precision": 9}
    ) == ("1977-01-01", 1)
    assert parse_wikidata_date(
        {"time": "+1977-05-00T00:00:00Z", "precision": 10}
    ) == ("1977-05-01", 2)
    assert parse_wikidata_date(
        {"time": "+1977-05-22T00:00:00Z", "precision": 11}
    ) == ("1977-05-22", 3)


def test_migrate_art_database_and_export(tmp_path, monkeypatch) -> None:
    source = SourceData(
        tags={
            1: SourceTag(1, "psychological_horror", "A mood tag."),
            2: SourceTag(2, "genre:adult_horror", None),
            3: SourceTag(
                3,
                "influence_person__Q905__surreal_dream_logic",
                "Influence of Luis Bunuel.",
            ),
            4: SourceTag(4, "influence_artist__elvis_presley", None),
        },
        pairs=[
            SourcePair(1, "Q10", 1),
            SourcePair(2, "Q10", 2),
            SourcePair(3, "Q10", 3),
            SourcePair(4, "Q10", 4),
        ],
        pair_refs={
            1: (100,),
            3: (300,),
            4: (400,),
        },
    )
    monkeypatch.setattr(model, "load_source_data", lambda path: source)

    layer_path = tmp_path / "film.jsonl"
    write_jsonl(
        layer_path,
        [
            {
                "id": "Q10",
                "layers": ["film"],
                "claims": {
                    "P1476": [{"text": "Test Film", "lang": "en"}],
                    "P577": [
                        {
                            "time": "+1977-05-00T00:00:00Z",
                            "precision": 10,
                            "calendar": "Q1985727",
                        }
                    ],
                    "P18": ["test.jpg"],
                    "P345": ["tt1234567"],
                    "P57": ["Q20"],
                    "P144": ["Q30"],
                },
            }
        ],
    )
    id_map_path = tmp_path / "id-map.jsonl"
    write_jsonl(
        id_map_path,
        [
            {"id": "Q20", "labels": {"en": "Director Person"}},
            {"id": "Q30", "labels": {"en": "Source Novel"}},
            {"id": "Q905", "labels": {"en": "Luis Bunuel"}},
        ],
    )

    db_path = tmp_path / "art.sqlite"
    stats = migrate_art_database(
        source_db=tmp_path / "source.duckdb",
        target_db=db_path,
        layer_paths=[layer_path],
        id_map_path=id_map_path,
    )

    assert stats.entities == 4
    assert stats.catalogued_entities == 1
    assert stats.secondary_entities == 3
    assert stats.tags == 4
    assert stats.entity_tags == 3
    assert stats.entity_links == 3
    assert stats.entity_tag_refs == 2
    assert stats.entity_link_refs == 1

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        work = db.execute(
            "select * from entities where is_catalogued = 1"
        ).fetchone()
        assert work["label"] == "Test Film"
        assert work["entity_kind"] == ENTITY_KIND_FILM
        assert work["release_date"] == "1977-05-01"
        assert work["date_precision"] == 2

        namespaced = db.execute(
            "select * from tags where tag_id = 2"
        ).fetchone()
        assert namespaced["tag_kind"] == TAG_KIND_NAMESPACED
        assert namespaced["namespace"] == "genre"
        assert namespaced["value"] == "adult_horror"

        legacy = db.execute("select * from tags where tag_id = 4").fetchone()
        assert legacy["tag_kind"] == TAG_KIND_LEGACY_RELATION_TEXT

        links = {
            row["link_kind"]: row
            for row in db.execute("select * from entity_links").fetchall()
        }
        assert links[LINK_KIND_INFLUENCED_BY]["weight"] == 50
        assert links[LINK_KIND_INFLUENCED_BY]["legacy_tag_id"] == 3
        assert links[LINK_KIND_ASSOCIATED]["weight"] == 25
        assert links[LINK_KIND_ADAPTED_FROM]["weight"] == 25
    finally:
        db.close()

    export_dir = tmp_path / "public" / "data"
    result = export_static_data(db_path, export_dir)
    assert result["catalog"] == 1

    catalog = json.loads((export_dir / "catalog.json").read_text())
    assert catalog[0]["label"] == "Test Film"
    assert catalog[0]["date"] == "1977-05-01"
    assert ["wikidata", "Q10"] in catalog[0]["refs"]
    assert ["imdb", "tt1234567"] in catalog[0]["refs"]
    assert len(catalog[0]["tags"]) == 3
    assert len(catalog[0]["links"]) == 3

    lookup = json.loads((export_dir / "entities-lookup.json").read_text())
    assert any(item["label"] == "Luis Bunuel" for item in lookup.values())


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
