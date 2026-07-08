from __future__ import annotations

import json
import sqlite3

import pytest

from art_islands import v2
from art_islands.model import REF_KIND_IMDB, REF_KIND_WIKIDATA
from tools.clean_domain_database import SCHEMA


def create_domain_fixture(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        db.execute("insert into data_sources values (1, 'legacy_database', 'Legacy', 'sqlite', null)")
        db.execute("insert into source_records values (1, 1, 'legacy:1', 'https://example.test/source')")
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
            "insert into entity_refs(entity_id, ref_kind, ref_value) values (?, ?, ?)",
            [
                (1, REF_KIND_WIKIDATA, "Q10"),
                (1, REF_KIND_IMDB, "tt1234567"),
                (2, REF_KIND_WIKIDATA, "Q20"),
            ],
        )
        db.executemany(
            """
            insert into tags(tag_id, name, description, tag_kind, namespace, value)
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (100, "genre:horror", None, 1, "genre", "horror"),
                (101, "dream_logic", "A migrated tag.", 0, None, None),
            ],
        )
        db.executemany(
            "insert into entity_tags(entity_id, tag_id, weight, polarity) values (?, ?, ?, ?)",
            [(1, 100, 80, 0), (1, 101, 55, -1)],
        )
        db.execute(
            """
            insert into entity_links(source_entity_id, target_entity_id, link_kind, weight, polarity)
            values (1, 2, 0, 70, 0)
            """
        )
        db.execute(
            """
            insert into entity_link_refs(source_entity_id, target_entity_id, link_kind, ref_id)
            values (1, 2, 0, 1)
            """
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
                entity_identifier_id, entity_id, identifier_scheme_id, value, is_primary, source_record_id
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, 1, "Q10", 1, 1),
                (2, 1, 2, "tt1234567", 1, 1),
                (3, 2, 1, "Q20", 1, 1),
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
            "insert into entity_types(entity_id, entity_type_id, is_primary, confidence, source_record_id) values (?, ?, ?, ?, ?)",
            [(1, 1, 1, 1.0, 1), (2, 2, 1, 1.0, 1)],
        )
        db.executemany(
            "insert into entity_texts(entity_id, text_kind, language, value, is_primary, source_record_id) values (?, ?, ?, ?, ?, ?)",
            [
                (1, "description", "en", "Layer description.", 1, 1),
                (2, "alias", "en", "Test Person", 0, 1),
            ],
        )
        db.executemany(
            "insert into relation_types values (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "director", "Director", "contributor", "work", "person", None),
                (2, "influenced_by", "Influenced by", "influence", "work", None, "influenced"),
            ],
        )
        db.execute(
            """
            insert into entity_relations(
                entity_relation_id, source_entity_id, target_entity_id, relation_type_id,
                role_label, character_label, ordering, weight, confidence, polarity, source_record_id
            )
            values (1, 1, 2, 1, null, null, 1, 70, 0.95, 0, 1)
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
                namespace, value, legacy_tag_id, classification_rule, confidence, review_recommended
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1000, "Horror", None, 1, None, "genre", "horror", 100, "namespace", 0.9, 0),
                (1001, "dream_logic", "A migrated tag.", 2, None, None, None, 101, "legacy", 0.6, 0),
            ],
        )
        db.executemany(
            """
            insert into entity_concepts(entity_id, concept_id, weight, polarity, confidence, source_record_id)
            values (?, ?, ?, ?, ?, ?)
            """,
            [(1, 1000, 80, 0, 0.9, 1), (1, 1001, 55, -1, 0.6, 1)],
        )
        db.execute(
            """
            insert into entity_dates(
                entity_date_id, entity_id, date_type, date_value, date_precision,
                rank, is_primary, confidence, source_record_id
            )
            values (1, 1, 'release', '1977-05-01', 2, 'compatibility', 1, 1.0, 1)
            """
        )
        db.execute("insert into measurement_types values (1, 'duration', 'Duration', 'seconds')")
        db.execute(
            """
            insert into entity_measurements(
                entity_measurement_id, entity_id, measurement_type_id,
                numeric_value, text_value, unit, qualifier, confidence, source_record_id
            )
            values (1, 1, 1, 7200, null, 'seconds', null, 0.9, 1)
            """
        )
        db.execute("insert into advisory_categories values (1, 'violence', 'Violence', null)")
        db.execute(
            """
            insert into entity_advisories(
                entity_advisory_id, entity_id, advisory_category_id, concept_id,
                severity, confidence, description, intensity, uncertainty
            )
            values (1, 1, 1, null, 3, 0.8, 'Stylized violence.', 62, 12)
            """
        )
        db.execute("insert into age_rating_systems values (1, 'mpaa', 'US', 'MPAA')")
        db.execute(
            """
            insert into entity_age_ratings(
                entity_age_rating_id, entity_id, age_rating_system_id, certificate,
                minimum_age, edition_label, descriptors_json, rating_date
            )
            values (1, 1, 1, 'R', 17, null, '[\"violence\"]', null)
            """
        )
        db.execute(
            """
            insert into entity_restrictions(
                entity_restriction_id, entity_id, country_code, restriction_type, reason, status
            )
            values (1, 1, 'US', 'restricted', 'Example restriction.', 'current')
            """
        )
        db.execute(
            "insert into patch_references(reference_id, kind, title, url, publisher, locator) values ('ref1', 'article', 'Example Article', 'https://example.test/ref', 'Example', 'p. 1')"
        )
        db.execute("insert into entity_tag_refs values (1, 100, 1)")
        db.execute("insert into entity_concept_patch_refs values (1, 1000, 'ref1')")
        db.execute("insert into entity_concept_source_refs values (1, 1000, 1)")
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
                dimension_values_json, context_json
            )
            values (1, 'violence', 'v1', 'film', 62, 40, 55, 70, 30, 45, 0, 50, 25, 0,
                    'teen', 'incidental', 'critical', null, 0.84, 12, '{\"blood\":20}', null)
            """
        )
        db.execute("insert into entity_content_guide_patch_refs values (1, 'violence', 'ref1')")
        db.execute("insert into entity_content_guide_source_refs values (1, 'violence', 1)")
        db.execute("insert into entity_advisory_patch_refs values (1, 'ref1')")
        db.execute("insert into entity_age_rating_patch_refs values (1, 'ref1')")
        db.execute("insert into entity_restriction_patch_refs values (1, 'ref1')")
        db.commit()
    finally:
        db.close()


def test_v2_exports_current_state_domain_data(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    output = tmp_path / "public" / "data" / "v2"
    create_domain_fixture(db_path)

    counts = v2.export_v2_static_data(db_path, output)

    assert counts == {"catalog": 1, "entities": 2, "relations": 1, "concepts": 2, "entity_concepts": 2}
    catalog = json.loads((output / "catalog.json").read_text(encoding="utf-8"))
    assert catalog[0]["contributors"]["director"] == [2]
    assert catalog[0]["concepts"]["genre"] == [1000]
    assert catalog[0]["measurements"] == [
        {"type": "duration", "number": 7200.0, "unit": "seconds", "confidence": 0.9}
    ]

    entities = json.loads((output / "entities.json").read_text(encoding="utf-8"))
    assert "completenessStatus" not in entities["1"]
    assert entities["1"]["identifiers"][0] == {"scheme": "imdb_title", "value": "tt1234567", "primary": True}

    relations = json.loads((output / "relations.json").read_text(encoding="utf-8"))
    assert relations[0]["type"] == "director"
    assert "manual" not in relations[0]

    concepts = json.loads((output / "concepts.json").read_text(encoding="utf-8"))
    assert "manual" not in concepts["entityConcepts"][0]
    advisories = json.loads((output / "advisories.json").read_text(encoding="utf-8"))
    assert advisories["advisories"][0]["intensity"] == 62


def test_advisories_export_includes_categories(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    output = tmp_path / "out"
    create_domain_fixture(db_path)

    v2.export_v2_static_data(db_path, output)

    payload = json.loads((output / "advisories.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert {c["code"] for c in payload["categories"]} == {"violence"}
    assert payload["categories"][0]["label"] == "Violence"
    row = payload["advisories"][0]
    assert set(row) <= {"id", "entityId", "categoryId", "conceptId", "severity", "intensity", "uncertainty"}
    assert "description" not in row


def test_ratings_export_includes_systems(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    output = tmp_path / "out"
    create_domain_fixture(db_path)

    v2.export_v2_static_data(db_path, output)

    payload = json.loads((output / "ratings.json").read_text(encoding="utf-8"))
    assert payload["systems"] == [{"id": 1, "code": "mpaa", "countryCode": "US", "label": "MPAA"}]
    assert payload["ratings"][0]["certificate"] == "R"
    assert payload["ratings"][0]["systemId"] == 1


def test_entities_export_has_no_texts(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    output = tmp_path / "out"
    create_domain_fixture(db_path)

    v2.export_v2_static_data(db_path, output)

    entities = json.loads((output / "entities.json").read_text(encoding="utf-8"))
    assert all("texts" not in entity for entity in entities.values())
    assert entities["1"]["description"] == "A compact test work."


def test_export_fails_on_corrupt_database(tmp_path) -> None:
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 4096)
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        v2.export_v2_static_data(bad, tmp_path / "out")


def test_v2_validation_checks_current_state_schema_and_sources(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    create_domain_fixture(db_path)

    result = v2.validate_v2_database(tmp_path, db_path, db_path)

    assert result["ok"] is True
    assert result["requiredTables"]["missing"] == []
    assert result["manualTagWeightPolarityMismatches"] == 0
    assert result["catalogQids"]["missingInV2"] == []
    assert result["externalIdentifiers"]["sourceRefsPreserved"] is True
    assert all(count == 0 for count in result["logicalSourceOrphans"].values())
    assert not (tmp_path / "tools" / "db_v2_migration").exists()


def test_v2_validation_detects_missing_legacy_tag_concept_assignment(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    create_domain_fixture(db_path)
    db = sqlite3.connect(db_path)
    try:
        db.execute("delete from entity_concept_patch_refs where entity_id = 1 and concept_id = 1001")
        db.execute("delete from entity_concept_source_refs where entity_id = 1 and concept_id = 1001")
        db.execute("delete from entity_concepts where entity_id = 1 and concept_id = 1001")
        db.commit()
    finally:
        db.close()

    result = v2.validate_v2_database(tmp_path, db_path, db_path)

    assert result["ok"] is False
    assert result["manualTagWeightPolarityMismatches"] == 1


def test_compact_schema_omits_technical_history_columns(tmp_path) -> None:
    db_path = tmp_path / "art-islands.sqlite"
    create_domain_fixture(db_path)
    db = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in db.execute("select name from sqlite_master where type = 'table'")
        }
        assert "schema_migrations" not in tables
        assert "data_patch_applications" not in tables
        assert "entity_concept_patch_metadata" not in tables

        columns = {
            table: {row[1] for row in db.execute(f"pragma table_info({table})")}
            for table in (
                "entities",
                "entity_concepts",
                "entity_relations",
                "entity_content_guide_dimensions",
                "source_records",
                "patch_references",
            )
        }
        assert {"created_at", "updated_at", "completeness_status", "review_state"}.isdisjoint(columns["entities"])
        assert "is_manual" not in columns["entity_concepts"]
        assert "is_manual" not in columns["entity_relations"]
        assert {"raw_json", "source_basis", "reference_ids_json"}.isdisjoint(
            columns["entity_content_guide_dimensions"]
        )
        assert {"local_path", "retrieved_at", "payload_hash", "revision_id", "metadata_json"}.isdisjoint(
            columns["source_records"]
        )
        assert {"raw_json", "updated_at", "source_record_id"}.isdisjoint(columns["patch_references"])
    finally:
        db.close()
