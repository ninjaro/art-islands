from __future__ import annotations

import json
import sqlite3

from art_islands import v2
from art_islands.schema import DOMAIN_SCHEMA


def create_domain_fixture(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(DOMAIN_SCHEMA)
        db.executemany(
            """
            insert into entities(
                entity_id, label, entity_kind, release_date, date_precision,
                is_catalogued, image_ref, short_description, entity_family
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "Test Work", 1, "1977-05-01", 2, 1, "work.jpg", "A compact test work.", "work"),
                (2, "Contributor", 3, None, 0, 0, None, "A contributor.", "person"),
            ],
        )
        db.executemany(
            """
            insert into identifier_schemes(
                identifier_scheme_id, code, label, entity_family, value_pattern, url_template
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "wikidata", "Wikidata", None, None, "https://www.wikidata.org/wiki/{value}"),
                (2, "imdb_title", "IMDb title", "work", None, "https://www.imdb.com/title/{value}/"),
            ],
        )
        db.executemany(
            """
            insert into entity_identifiers(
                entity_identifier_id, entity_id, identifier_scheme_id, value, is_primary
            )
            values (?, ?, ?, ?, ?)
            """,
            [
                (1, 1, 1, "Q10", 1),
                (2, 1, 2, "tt1234567", 1),
                (3, 2, 1, "Q20", 1),
            ],
        )
        db.executemany(
            "insert into entity_type_definitions values (?, ?, ?, ?, ?)",
            [
                (1, "film", "work", "Film", "Motion picture."),
                (2, "person", "person", "Person", "Human contributor."),
            ],
        )
        db.executemany(
            "insert into entity_types(entity_id, entity_type_id, is_primary, confidence) values (?, ?, ?, ?)",
            [(1, 1, 1, 1.0), (2, 2, 1, 1.0)],
        )
        db.executemany(
            "insert into entity_texts(entity_id, text_kind, language, value, is_primary) values (?, ?, ?, ?, ?)",
            [
                (1, "description", "en", "Layer description.", 1),
                (2, "alias", "en", "Test Person", 0),
            ],
        )
        db.executemany(
            "insert into relation_types values (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "director", "Director", "contributor", "work", "person", None),
                (2, "adapted_from", "Adapted from", "semantic", "work", "work", None),
            ],
        )
        db.execute(
            """
            insert into entity_relations(
                entity_relation_id, source_entity_id, target_entity_id, relation_type_id, weight, confidence
            )
            values (1, 1, 2, 1, 70, 0.95)
            """
        )
        db.executemany(
            "insert into concept_categories values (?, ?, ?)",
            [(1, "genre", "Genre"), (2, "other", "Other")],
        )
        db.executemany(
            """
            insert into concepts(
                concept_id, label, description, concept_category_id, canonical_entity_id,
                namespace, value, confidence
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1000, "Horror", None, 1, None, "genre", "horror", 0.9),
                (1001, "dream_logic", "A migrated tag.", 2, None, None, None, 0.6),
            ],
        )
        db.executemany(
            """
            insert into entity_concepts(entity_id, concept_id, weight, polarity, confidence)
            values (?, ?, ?, ?, ?)
            """,
            [(1, 1000, 80, 0, 0.9), (1, 1001, None, -1, 0.6)],
        )
        db.execute(
            """
            insert into entity_dates(
                entity_date_id, entity_id, date_type, date_value, date_precision,
                rank, is_primary, confidence
            )
            values (1, 1, 'release', '1977-05-01', 2, 'compatibility', 1, 1.0)
            """
        )
        db.execute("insert into measurement_types values (1, 'duration', 'Duration', 'seconds')")
        db.execute(
            """
            insert into entity_measurements(
                entity_measurement_id, entity_id, measurement_type_id,
                numeric_value, unit, confidence
            )
            values (1, 1, 1, 7200, 'seconds', 0.9)
            """
        )
        db.execute(
            """
            insert into source_references(reference_id, source_type, title, url, publisher, locator)
            values ('ref1', 'article', 'Example Article', 'https://example.test/ref', 'Example', 'p. 1')
            """
        )
        db.execute("insert into entity_concept_references values (1, 1000, 'ref1')")
        db.execute(
            "insert into content_guide_categories values ('violence', 'Violence', 'Violence score.', 1, 0, 100, 'v1')"
        )
        db.execute(
            """
            insert into entity_content_guide_dimensions(
                entity_id, category_code, scale_version, medium, intensity,
                centrality, explicitness, realism, recurrence, sensory_impact,
                coercion, avoidance_priority, narrative_proximity, language_dependency,
                guidance_level, content_role, stance, genre_context, confidence, uncertainty,
                description, dimension_values_json, context_json
            )
            values (1, 'violence', 'v1', 'film', 62, 40, 55, 70, 30, 45, 0, 50, 25, 0,
                    'teen', 'incidental', 'critical', null, 0.84, 12, 'Stylized violence.',
                    '{"blood":20}', '{"presentationModes":["stylized"]}')
            """
        )
        db.execute("insert into entity_content_guide_references values (1, 'violence', 'ref1')")
        db.execute(
            """
            insert into entity_restrictions(
                entity_restriction_id, entity_id, country_code, restriction_type, reason, status
            )
            values (1, 1, 'US', 'restricted', 'Example restriction.', 'current')
            """
        )
        db.execute("insert into entity_restriction_references values (1, 'ref1')")
        db.commit()
    finally:
        db.close()


def test_v2_exports_current_state_domain_data(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    output = tmp_path / "public" / "data" / "v2"
    create_domain_fixture(db_path)

    counts = v2.export_v2_static_data(db_path, output)

    assert counts == {"catalog": 1, "entities": 2, "relations": 1, "concepts": 2, "entity_concepts": 2}
    assert not (output / "ratings.json").exists()

    catalog = json.loads((output / "catalog.json").read_text(encoding="utf-8"))
    assert catalog[0]["contributors"]["director"] == [2]
    assert catalog[0]["concepts"]["genre"] == [1000]
    assert catalog[0]["measurements"] == [
        {"type": "duration", "number": 7200.0, "unit": "seconds", "confidence": 0.9}
    ]

    entities = json.loads((output / "entities.json").read_text(encoding="utf-8"))
    assert entities["1"]["identifiers"][0] == {"scheme": "imdb_title", "value": "tt1234567", "primary": True}

    concepts = json.loads((output / "concepts.json").read_text(encoding="utf-8"))
    assert concepts["entityConcepts"][1]["weight"] is None
    assert "legacyTagId" not in concepts["concepts"][0]

    advisories = json.loads((output / "advisories.json").read_text(encoding="utf-8"))
    assert advisories["categories"][0]["code"] == "violence"
    assert advisories["advisories"][0]["categoryCode"] == "violence"
    assert advisories["advisories"][0]["intensity"] == 62
    assert advisories["advisories"][0]["description"] == "Stylized violence."


def test_v2_validation_uses_compact_references(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    create_domain_fixture(db_path)

    result = v2.validate_v2_database(tmp_path, db_path, db_path)

    assert result["ok"] is True
    assert result["requiredTables"]["missing"] == []
    assert result["logicalReferenceOrphans"] == {
        "entityConceptReferences": 0,
        "entityContentGuideReferences": 0,
        "entityRestrictionReferences": 0,
    }


def test_compact_schema_excludes_removed_legacy_tables(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    create_domain_fixture(db_path)
    db = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in db.execute("select name from sqlite_master where type = 'table'")}
    finally:
        db.close()

    assert "tags" not in tables
    assert "entity_tags" not in tables
    assert "entity_refs" not in tables
    assert "entity_advisories" not in tables
    assert "entity_age_ratings" not in tables
