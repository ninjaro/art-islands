from __future__ import annotations

from art_islands.evolution import (
    EVOLUTION_NOTE,
    LineageWork,
    build_evolution_export,
    compute_lineage,
)
from art_islands.model import connect_art, settings_with_defaults


def work(entity_id, date, tags, kind=1):
    return LineageWork(
        entity_id=entity_id,
        kind=kind,
        date=date,
        year=int(date[:4]),
        tags=tuple(tags),
    )


def lineage(works, **overrides):
    params = {"minimum_similarity": 0.1, "minimum_shared_tags": 2}
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
        work(2, "1960-01-01", [(99, 80), (98, 60)]),  # no tags in common
        work(3, "1970-01-01", [(10, 5)]),  # only one weak shared tag
    ]
    records = {record.entity_id: record for record in lineage(works)}
    assert records[1].parent_id is None
    assert records[2].parent_id is None
    assert records[3].parent_id is None


def test_common_generic_tags_are_downweighted() -> None:
    generic = 500
    works = []
    # Tag 500 appears on every work: it must not create lineage on its own.
    for index in range(1, 30):
        works.append(work(index, f"{1900 + index}-01-01", [(generic, 100), (index, 100)]))
    # Two works genuinely share two specific tags.
    works.append(work(100, "1980-01-01", [(generic, 100), (70, 90), (71, 90)]))
    works.append(work(101, "1985-01-01", [(generic, 100), (70, 90), (71, 90)]))

    records = {record.entity_id: record for record in lineage(works)}
    # The specific overlap wins for 101.
    assert records[101].parent_id == 100
    # Works that only share the generic tag stay roots.
    assert records[5].parent_id is None


def test_same_kind_preferred_over_other_kinds() -> None:
    works = [
        work(1, "1950-01-01", [(10, 90), (11, 90)], kind=2),
        work(2, "1951-01-01", [(10, 90), (11, 90)], kind=1),
        work(3, "1960-01-01", [(10, 90), (11, 90)], kind=1),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    assert records[3].parent_id == 2


def test_edge_metadata_explains_inference() -> None:
    works = [
        work(1, "1950-01-01", [(10, 90), (11, 80), (12, 70)]),
        work(2, "1960-01-01", [(10, 90), (11, 80), (12, 70)]),
    ]
    records = {record.entity_id: record for record in lineage(works)}
    child = records[2]
    assert child.parent_id == 1
    assert child.score > 0
    assert child.shared_tags == 3
    assert set(child.top_tags) <= {10, 11, 12}
    assert len(child.top_tags) <= 3


def test_export_includes_undated_works_as_roots(tmp_path) -> None:
    db = connect_art(tmp_path / "art.sqlite")
    db.executemany(
        """
        insert into entities(entity_id, label, entity_kind, release_date, date_precision, is_catalogued)
        values (?, ?, 1, ?, ?, 1)
        """,
        [
            (1, "Old", "1950-01-01", 3),
            (2, "New", "1960-01-01", 3),
            (3, "Undated", None, 0),
        ],
    )
    db.executemany(
        "insert into tags(tag_id, name) values (?, ?)",
        [(10, "alpha"), (11, "beta")],
    )
    db.executemany(
        "insert into entity_tags(entity_id, tag_id, weight, polarity) values (?, ?, ?, 0)",
        [(1, 10, 90), (1, 11, 90), (2, 10, 90), (2, 11, 90), (3, 10, 90)],
    )
    db.commit()

    export = build_evolution_export(db, settings_with_defaults())
    db.close()

    assert export["version"] == 1
    assert export["note"] == EVOLUTION_NOTE
    nodes = {node["id"]: node for node in export["nodes"]}
    assert set(nodes) == {1, 2, 3}
    assert nodes[1]["parent"] is None
    assert nodes[2]["parent"] == 1
    assert nodes[3]["parent"] is None
    # No fabricated ids: every referenced parent exists.
    for node in export["nodes"]:
        assert node["parent"] is None or node["parent"] in nodes
