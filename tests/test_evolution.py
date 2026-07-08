from __future__ import annotations

import sqlite3

from art_islands import features
from art_islands.evolution import (
    EVOLUTION_NOTE,
    LineageWork,
    build_evolution_export,
    compute_lineage,
)
from art_islands.model import DEFAULT_SETTINGS, settings_with_defaults
from art_islands.schema import DOMAIN_SCHEMA

SETTINGS = DEFAULT_SETTINGS["features"]


def concept_features(concepts, contributors=(), advisories=()):
    return features.extract_features(
        [(cid, f"Concept {cid}", "Genre", weight, polarity) for cid, weight, polarity in concepts],
        contributors,
        advisories,
        SETTINGS,
    )


def work(entity_id, date, concepts, kind="film", contributors=(), advisories=()):
    normalized = [entry if len(entry) == 3 else (*entry, 0) for entry in concepts]
    return LineageWork(
        entity_id=entity_id,
        kind=kind,
        date=date,
        year=int(date[:4]),
        features=concept_features(normalized, contributors, advisories),
    )


def lineage(works, **overrides):
    params = {"minimum_similarity": 0.1, "minimum_shared_features": 2}
    params.update(overrides)
    return compute_lineage(works, **params)


def test_parent_is_always_strictly_earlier() -> None:
    works = [
        work(1, "1950-01-01", [(10, 80), (11, 60)]),
        work(2, "1960-01-01", [(10, 80), (11, 60)]),
        work(3, "1960-01-01", [(10, 80), (11, 60)]),
        work(4, "1970-01-01", [(10, 80), (11, 60)]),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    dates = {1: "1950-01-01", 2: "1960-01-01", 3: "1960-01-01", 4: "1970-01-01"}

    for record in records.values():
        if record.parent_id is not None:
            assert dates[record.parent_id] < dates[record.entity_id]
            assert record.parent_id != record.entity_id

    # Works sharing a date must not parent each other.
    assert records[2].parent_id == 1
    assert records[3].parent_id == 1


def test_no_cycles_and_single_parent() -> None:
    works = [
        work(index, f"{1900 + index}-01-01", [(10, 80), (11, 70), (12 + index % 3, 50)])
        for index in range(1, 40)
    ]
    records = lineage(works)

    parents = {record.entity_id: record.parent_id for record in records}
    assert len(parents) == len(works)  # exactly one record per work

    for start in parents:
        seen = set()
        node = start
        while node is not None:
            assert node not in seen, "cycle detected"
            seen.add(node)
            node = parents[node]


def test_deterministic_output() -> None:
    works = [
        work(index, f"{1900 + index % 30}-0{1 + index % 9}-01", [(10 + index % 7, 40 + index % 60), (20, 70)])
        for index in range(1, 120)
    ]
    first = lineage(list(works))
    second = lineage(list(reversed(works)))
    assert first == second


def test_weakly_related_records_become_roots() -> None:
    works = [
        work(1, "1950-01-01", [(10, 80), (11, 60)]),
        work(2, "1960-01-01", [(99, 80), (98, 60)]),  # no features in common
        work(3, "1970-01-01", [(10, 5)]),  # only one weak shared feature
    ]
    records = {record.entity_id: record for record in lineage(works)}
    assert records[1].parent_id is None
    assert records[2].parent_id is None
    assert records[3].parent_id is None


def test_common_generic_features_are_downweighted() -> None:
    generic = 500
    works = []
    # Concept 500 appears on every work: it must not create lineage on its own.
    for index in range(1, 30):
        works.append(work(index, f"{1900 + index}-01-01", [(generic, 100), (index, 100)]))
    # Two works genuinely share two specific concepts.
    works.append(work(100, "1980-01-01", [(generic, 100), (70, 90), (71, 90)]))
    works.append(work(101, "1985-01-01", [(generic, 100), (70, 90), (71, 90)]))

    records = {record.entity_id: record for record in lineage(works)}
    # The specific overlap wins for 101.
    assert records[101].parent_id == 100
    # Works that only share the generic concept stay roots.
    assert records[5].parent_id is None


def test_same_kind_preferred_over_other_kinds() -> None:
    works = [
        work(1, "1950-01-01", [(10, 90), (11, 90)], kind="music"),
        work(2, "1951-01-01", [(10, 90), (11, 90)], kind="film"),
        work(3, "1960-01-01", [(10, 90), (11, 90)], kind="film"),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    assert records[3].parent_id == 2


def test_kind_preference_is_configurable_not_a_partition() -> None:
    works = [
        work(1, "1950-01-01", [(10, 90), (11, 90)], kind="music"),
        work(2, "1980-01-01", [(10, 90), (11, 90)], kind="film"),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    # A cross-kind parent is still assigned when it is the only evidence.
    assert records[2].parent_id == 1


def test_shared_director_connects_works_without_shared_concepts() -> None:
    director = [(50, "R. Scott", "person", "director", 80, 0)]
    works = [
        work(1, "1979-01-01", [(10, 80)], contributors=director),
        work(2, "1982-01-01", [(11, 80)], contributors=director),
    ]
    records = {
        record.entity_id: record
        for record in lineage(works, minimum_shared_features=1, minimum_similarity=0.05)
    }
    assert records[2].parent_id == 1
    factor = records[2].top_factors[0]
    assert factor["id"] == "entity:50"
    assert factor["label"] == "R. Scott"
    assert factor["source"] == "contributor"


def test_negative_polarity_reduces_parent_score() -> None:
    works = [
        work(1, "1950-01-01", [(10, 80, 0), (11, 60, 0)]),
        work(2, "1950-06-01", [(10, 80, 0), (11, 60, -1)]),
        work(3, "1960-01-01", [(10, 80, 0), (11, 60, 0)]),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    # The fully aligned earlier work wins over the polarity-conflicting one.
    assert records[3].parent_id == 1


def test_edge_metadata_explains_inference() -> None:
    works = [
        work(1, "1950-01-01", [(10, 90), (11, 80), (12, 70)]),
        work(2, "1960-01-01", [(10, 90), (11, 80), (12, 70)]),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    child = records[2]
    assert child.parent_id == 1
    assert child.score > 0
    assert child.shared_features == 3
    assert len(child.top_factors) <= 3
    for factor in child.top_factors:
        assert factor["label"].startswith("Concept ")
        assert factor["contribution"] > 0
        assert factor["source"] == "direct-concept"


def create_v2_evolution_fixture(path) -> None:
    db = sqlite3.connect(path)
    try:
        db.executescript(DOMAIN_SCHEMA)
        db.executemany(
            """
            insert into entities(
                entity_id, label, entity_kind, release_date, date_precision,
                is_catalogued, image_ref, short_description, entity_family
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "Early Film", 1, "1980-01-01", 1, 1, None, None, "work"),
                (2, "Later Film", 1, "1990-01-01", 1, 1, None, None, "work"),
                (3, "Famous Director", 3, "1940-01-01", 1, 1, None, None, "person"),
                (4, "Undated Work", 7, None, 0, 1, None, None, "work"),
            ],
        )
        db.executemany(
            "insert into entity_type_definitions values (?, ?, ?, ?, ?)",
            [(1, "film", "work", "Film", None), (2, "person", "person", "Person", None)],
        )
        db.executemany(
            "insert into entity_types(entity_id, entity_type_id, is_primary, confidence) values (?, ?, ?, ?)",
            [(1, 1, 1, 1.0), (2, 1, 1, 1.0), (3, 2, 1, 1.0)],
        )
        db.execute(
            "insert into relation_types values (1, 'director', 'Director', 'contributor', 'work', 'person', null)"
        )
        db.executemany(
            """
            insert into entity_relations(
                entity_relation_id, source_entity_id, target_entity_id, relation_type_id, weight, confidence
            ) values (?, ?, ?, ?, ?, 0.9)
            """,
            [(1, 1, 3, 1, 80), (2, 2, 3, 1, 80)],
        )
        db.execute("insert into concept_categories values (1, 'genre', 'Genre')")
        db.executemany(
            """
            insert into concepts(
                concept_id, label, description, concept_category_id, canonical_entity_id,
                namespace, value, confidence
            ) values (?, ?, null, 1, null, null, null, 0.9)
            """,
            [(100, "Sci-fi"), (101, "Only Early"), (102, "Only Later")],
        )
        db.executemany(
            "insert into entity_concepts(entity_id, concept_id, weight, polarity, confidence) values (?, ?, ?, ?, 0.9)",
            [(1, 100, 90, 0), (2, 100, 90, 0), (1, 101, 50, 0), (2, 102, 50, 0)],
        )
        db.execute("insert into content_guide_categories values ('violence', 'Violence', null, 1, 0, 100, 'v1')")
        db.executemany(
            """
            insert into entity_content_guide_dimensions(
                entity_id, category_code, confidence, intensity, uncertainty
            ) values (?, 'violence', 0.8, ?, 10)
            """,
            [(1, 70), (2, 72)],
        )
        db.commit()
    finally:
        db.close()


def test_v2_export_uses_features_and_excludes_people(tmp_path) -> None:
    db_path = tmp_path / "domain.sqlite"
    create_v2_evolution_fixture(db_path)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    export = build_evolution_export(db, settings_with_defaults())
    db.close()

    assert export["version"] == 2
    assert export["note"] == EVOLUTION_NOTE
    nodes = {node["id"]: node for node in export["nodes"]}
    # The catalogued person never becomes an Evolution node.
    assert set(nodes) == {1, 2, 4}
    assert nodes[1]["parent"] is None
    assert nodes[2]["parent"] == 1
    assert nodes[4]["parent"] is None

    evidence = nodes[2]["evidence"]
    assert evidence["score"] > 0
    assert evidence["sharedFeatureCount"] == 3  # shared concept + director + advisory profile
    labels = {factor["label"] for factor in evidence["topFactors"]}
    assert labels <= {"Sci-fi", "Famous Director", "Violence"}
    sources = {factor["source"] for factor in evidence["topFactors"]}
    assert sources <= {"direct-concept", "contributor", "content-guide"}
    # Explanations are human-readable, never bare ids.
    assert all(not factor["label"].startswith("concept:") for factor in evidence["topFactors"])

    rerun_db = sqlite3.connect(db_path)
    rerun_db.row_factory = sqlite3.Row
    second = build_evolution_export(rerun_db, settings_with_defaults())
    rerun_db.close()
    assert second == export  # deterministic
