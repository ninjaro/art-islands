from __future__ import annotations

import json
import sqlite3

import pytest

from art_islands import v2
from art_islands.model import (
    LINK_KIND_INFLUENCED_BY,
    REF_KIND_IMDB,
    REF_KIND_WIKIDATA,
    connect_art,
)
from art_islands.schema import MigrationError, migration_status


def write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def create_v1_fixture(path) -> None:
    db = connect_art(path)
    try:
        db.executemany(
            """
            insert into entities(
                entity_id, label, entity_kind, release_date,
                date_precision, is_catalogued, image_ref
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "Test Work", 1, "1977-05-01", 2, 1, "work.jpg"),
                (2, "Contributor", 3, None, 0, 0, None),
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
            insert into entity_links(
                source_entity_id, target_entity_id, link_kind, weight, polarity
            )
            values (1, 2, ?, 70, 0)
            """,
            (LINK_KIND_INFLUENCED_BY,),
        )
        db.commit()
    finally:
        db.close()


def test_v2_migrates_existing_database_and_exports(tmp_path) -> None:
    project = tmp_path / "repo"
    source = project / "data" / "art-islands.sqlite"
    target = project / "data" / "art-islands-v2.sqlite"
    create_v1_fixture(source)

    result = v2.migrate_existing_database(project, source, target)
    assert result["validation"]["ok"] is True
    assert target.exists()
    assert result["backup"] is None
    assert not list((project / "data").glob("art-islands.backup-*.sqlite"))

    db = sqlite3.connect(target)
    db.row_factory = sqlite3.Row
    try:
        assert db.execute("select count(*) from schema_migrations").fetchone()[0] == 6
        assert db.execute("select count(*) from entity_identifiers").fetchone()[0] == 3
        assert db.execute("select count(*) from entity_dates").fetchone()[0] == 1
        concept = db.execute(
            """
            select cc.code, ec.weight, ec.polarity
            from entity_concepts ec
            join concepts c on c.concept_id = ec.concept_id
            join concept_categories cc on cc.concept_category_id = c.concept_category_id
            where ec.entity_id = 1 and c.legacy_tag_id = 100
            """
        ).fetchone()
        assert dict(concept) == {"code": "genre", "weight": 80, "polarity": 0}
        relation = db.execute(
            """
            select t.code, r.weight
            from entity_relations r
            join relation_types t on t.relation_type_id = r.relation_type_id
            """
        ).fetchone()
        assert dict(relation) == {"code": "influenced_by", "weight": 70}
    finally:
        db.close()

    output = project / "public" / "data" / "v2"
    counts = v2.export_v2_static_data(target, output)
    assert counts["catalog"] == 1
    assert counts["entities"] == 2
    catalog = json.loads((output / "catalog.json").read_text(encoding="utf-8"))
    assert catalog[0]["contributors"]["influenced_by"] == [2]
    assert catalog[0]["concepts"]["genre"] == [100]


def test_enrich_local_applies_indexed_layer_rows(tmp_path) -> None:
    project = tmp_path / "repo"
    source_root = tmp_path
    source = project / "data" / "art-islands.sqlite"
    target = project / "data" / "art-islands-v2.sqlite"
    create_v1_fixture(source)
    v2.migrate_existing_database(project, source, target)
    write_jsonl(
        source_root / "layers" / "film.jsonl",
        [
            {
                "id": "Q10",
                "layers": ["film"],
                "claims": {
                    "P18": ["poster.jpg"],
                    "P57": ["Q20"],
                    "P136": ["Q30"],
                    "P345": ["tt7654321"],
                    "P577": [{"time": "+1977-05-25T00:00:00Z", "precision": 11}],
                    "P2047": [{"amount": "+120", "unit": "Q7727"}],
                },
            }
        ],
    )
    write_jsonl(
        source_root / "layers" / "id_map.slow.partial.jsonl",
        [
            {
                "id": "Q10",
                "labels": {"en": "Test Work"},
                "descriptions": {"en": "Layer description."},
            },
            {
                "id": "Q20",
                "labels": {"en": "Contributor"},
                "descriptions": {"en": "A contributor."},
            },
            {"id": "Q30", "labels": {"en": "Horror"}, "descriptions": {"en": "Genre."}},
        ],
    )

    result = v2.enrich_local(project, target, source_root=source_root, qids={"Q10"})
    assert result["indexRecords"] == 1
    assert result["relations"] >= 1
    assert result["concepts"] >= 1
    assert result["measurements"] == 1

    db = sqlite3.connect(target)
    db.row_factory = sqlite3.Row
    try:
        entity = db.execute("select release_date, date_precision, image_ref from entities where entity_id = 1").fetchone()
        assert dict(entity) == {
            "release_date": "1977-05-25",
            "date_precision": 3,
            "image_ref": "work.jpg",
        }
        assert db.execute("select count(*) from entity_concepts where is_manual = 1").fetchone()[0] == 0
        assert db.execute(
            """
            select count(*)
            from entity_relations r
            join relation_types t on t.relation_type_id = r.relation_type_id
            where t.code = 'director'
            """
        ).fetchone()[0] == 1
        measurement = db.execute(
            """
            select m.numeric_value, m.unit
            from entity_measurements m
            join measurement_types t on t.measurement_type_id = m.measurement_type_id
            where t.code = 'duration'
            """
        ).fetchone()
        assert tuple(measurement) == (7200.0, "seconds")
    finally:
        db.close()


def test_schema_checksum_validation_detects_modified_applied_migration(tmp_path) -> None:
    project = tmp_path / "repo"
    source = project / "data" / "art-islands.sqlite"
    target = project / "data" / "art-islands-v2.sqlite"
    create_v1_fixture(source)
    v2.migrate_existing_database(project, source, target)

    db = connect_art(target)
    try:
        db.execute(
            "update schema_migrations set checksum = 'bad' where version = 1"
        )
        db.commit()
        with pytest.raises(MigrationError, match="checksum"):
            migration_status(db)
    finally:
        db.close()


def test_layer_index_streams_jsonl_and_records_offsets(tmp_path) -> None:
    project = tmp_path / "repo"
    source_root = tmp_path
    write_jsonl(
        source_root / "layers" / "film.jsonl",
        [
            {"id": "Q1", "claims": {"P31": ["Q11424"]}, "layers": ["film"]},
            {"id": "Q2", "claims": {}, "layers": ["film"]},
        ],
    )

    result = v2.build_layer_index(
        project,
        source_root,
        layers=["film"],
        qids={"Q2"},
        resume=True,
    )
    assert result["records"] == 1

    db = sqlite3.connect(project / "tools" / "db_v2_migration" / "cache" / "layer_index.sqlite")
    try:
        row = db.execute(
            "select qid, byte_offset, byte_length from layer_records"
        ).fetchone()
        assert row[0] == "Q2"
        assert row[1] > 0
        assert row[2] > 0
    finally:
        db.close()
