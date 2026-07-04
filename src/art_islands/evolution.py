"""Build-time inferred lineage ("Evolution") calculation.

The result is an inferred temporal similarity structure, not proven
historical influence. Every edge stores the evidence supporting it
(similarity score, shared tag count, strongest shared tags) so the UI can
explain it without claiming factual influence.

Hard invariants:

* a parent is strictly earlier than its child;
* a node has zero or one parent;
* no self-parent and no cycles (guaranteed by strict date ordering);
* no fabricated entity ids;
* deterministic results for identical inputs.

Candidate generation is bounded through a tag-to-entity index over earlier
works instead of a quadratic all-pairs comparison. Extremely common tags are
downweighted by inverse document frequency and skipped entirely for
candidate generation.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

EVOLUTION_NOTE = (
    "Branches are inferred from date and tag similarity. "
    "They do not prove direct influence."
)

# Tags carried by more works than this are still used for scoring (with a
# low IDF weight) but never for candidate generation.
CANDIDATE_TAG_DF_CAP = 150

# Preference multiplier applied to candidates of a different broad work kind.
KIND_MISMATCH_FACTOR = 0.6

# Mild temporal-distance penalty half-life, in years. Long historical
# branches stay possible: a 75-year gap halves the ranking score.
TEMPORAL_HALF_LIFE_YEARS = 75.0

TOP_SHARED_TAGS = 3


@dataclass(frozen=True)
class LineageWork:
    entity_id: int
    kind: int
    date: str
    year: int
    tags: tuple[tuple[int, int], ...]  # (tag_id, weight 0-100)


@dataclass(frozen=True)
class LineageRecord:
    entity_id: int
    parent_id: int | None
    score: float
    shared_tags: int
    top_tags: tuple[int, ...]


def broad_kind(kind: int) -> str:
    if kind == 1:
        return "film"
    if kind == 2:
        return "music"
    if kind == 6:
        return "game"
    return "work"


def load_catalogued_works(db: sqlite3.Connection) -> list[LineageWork]:
    rows = db.execute(
        """
        select entity_id, entity_kind, release_date
        from entities
        where is_catalogued = 1
        order by entity_id
        """
    ).fetchall()
    tag_rows = db.execute(
        """
        select entity_id, tag_id, weight
        from entity_tags
        order by entity_id, tag_id
        """
    ).fetchall()

    tags_by_entity: defaultdict[int, list[tuple[int, int]]] = defaultdict(list)
    for row in tag_rows:
        tags_by_entity[int(row["entity_id"])].append((int(row["tag_id"]), int(row["weight"])))

    works: list[LineageWork] = []
    for row in rows:
        date = row["release_date"]
        if not date:
            continue  # undated works cannot be ordered; they become roots
        works.append(
            LineageWork(
                entity_id=int(row["entity_id"]),
                kind=int(row["entity_kind"]),
                date=str(date),
                year=int(str(date)[:4]),
                tags=tuple(tags_by_entity.get(int(row["entity_id"]), ())),
            )
        )
    return works


def compute_lineage(
    works: list[LineageWork],
    *,
    minimum_similarity: float,
    minimum_shared_tags: int,
    candidate_tag_df_cap: int = CANDIDATE_TAG_DF_CAP,
) -> list[LineageRecord]:
    """Assign at most one strictly-earlier parent per work."""

    total = max(1, len(works))
    document_frequency: defaultdict[int, int] = defaultdict(int)
    for work in works:
        for tag_id, _ in work.tags:
            document_frequency[tag_id] += 1

    idf = {
        tag_id: math.log(1 + total / df)
        for tag_id, df in document_frequency.items()
    }

    vectors: dict[int, dict[int, float]] = {}
    norms: dict[int, float] = {}
    for work in works:
        vector = {
            tag_id: (min(max(weight, 0), 100) / 100.0) * idf[tag_id]
            for tag_id, weight in work.tags
        }
        vector = {tag_id: value for tag_id, value in vector.items() if value > 0}
        vectors[work.entity_id] = vector
        norms[work.entity_id] = math.sqrt(sum(value * value for value in vector.values()))

    ordered = sorted(works, key=lambda work: (work.date, work.entity_id))

    # Postings over strictly earlier works only. Works sharing the same date
    # are added after the whole date group is processed, so a parent is
    # always strictly earlier than its child.
    postings: defaultdict[int, list[int]] = defaultdict(list)
    processed: dict[int, LineageWork] = {}
    records: list[LineageRecord] = []

    index = 0
    while index < len(ordered):
        group_end = index
        current_date = ordered[index].date
        while group_end < len(ordered) and ordered[group_end].date == current_date:
            group_end += 1
        group = ordered[index:group_end]

        for work in group:
            record = _best_parent(
                work,
                postings=postings,
                processed=processed,
                vectors=vectors,
                norms=norms,
                candidate_tag_df_cap=candidate_tag_df_cap,
                document_frequency=document_frequency,
                minimum_similarity=minimum_similarity,
                minimum_shared_tags=minimum_shared_tags,
            )
            records.append(record)

        for work in group:
            processed[work.entity_id] = work
            for tag_id, _ in work.tags:
                if document_frequency[tag_id] <= candidate_tag_df_cap:
                    postings[tag_id].append(work.entity_id)

        index = group_end

    records.sort(key=lambda record: record.entity_id)
    return records


def _best_parent(
    work: LineageWork,
    *,
    postings: dict[int, list[int]],
    processed: dict[int, LineageWork],
    vectors: dict[int, dict[int, float]],
    norms: dict[int, float],
    candidate_tag_df_cap: int,
    document_frequency: dict[int, int],
    minimum_similarity: float,
    minimum_shared_tags: int,
) -> LineageRecord:
    vector = vectors[work.entity_id]
    norm = norms[work.entity_id]
    if not vector or norm == 0:
        return LineageRecord(work.entity_id, None, 0.0, 0, ())

    candidates: set[int] = set()
    for tag_id in vector:
        if document_frequency.get(tag_id, 0) > candidate_tag_df_cap:
            continue
        candidates.update(postings.get(tag_id, ()))

    best: tuple[float, float, str, int] | None = None  # (adjusted, raw, date, id)
    best_shared: list[tuple[float, int]] = []

    for candidate_id in sorted(candidates):
        other = processed[candidate_id]
        other_vector = vectors[candidate_id]
        other_norm = norms[candidate_id]
        if other_norm == 0:
            continue

        small, large = (
            (vector, other_vector) if len(vector) <= len(other_vector) else (other_vector, vector)
        )
        dot = 0.0
        shared: list[tuple[float, int]] = []
        for tag_id, value in small.items():
            other_value = large.get(tag_id)
            if other_value is None:
                continue
            contribution = value * other_value
            dot += contribution
            shared.append((contribution, tag_id))

        if len(shared) < minimum_shared_tags:
            continue
        similarity = dot / (norm * other_norm)
        if similarity < minimum_similarity:
            continue

        kind_factor = 1.0 if broad_kind(other.kind) == broad_kind(work.kind) else KIND_MISMATCH_FACTOR
        years = max(0, work.year - other.year)
        temporal_factor = 1.0 / (1.0 + years / TEMPORAL_HALF_LIFE_YEARS)
        adjusted = similarity * kind_factor * temporal_factor

        # Deterministic tie-breaks: stronger adjusted score, then later
        # (closer) parent date, then smaller entity id.
        key = (adjusted, similarity, other.date, -candidate_id)
        if best is None or key > (best[0], best[1], best[2], -best[3]):
            best = (adjusted, similarity, other.date, candidate_id)
            best_shared = shared

    if best is None:
        return LineageRecord(work.entity_id, None, 0.0, 0, ())

    best_shared.sort(key=lambda entry: (-entry[0], entry[1]))
    return LineageRecord(
        entity_id=work.entity_id,
        parent_id=best[3],
        score=round(best[1], 4),
        shared_tags=len(best_shared),
        top_tags=tuple(tag_id for _, tag_id in best_shared[:TOP_SHARED_TAGS]),
    )


def build_evolution_export(
    db: sqlite3.Connection,
    settings: dict[str, Any],
) -> dict[str, Any]:
    evolution_settings = settings.get("evolution", {})
    minimum_similarity = float(evolution_settings.get("minimumSimilarity", 0.18))
    minimum_shared_tags = int(evolution_settings.get("minimumSharedTags", 2))

    works = load_catalogued_works(db)
    records = compute_lineage(
        works,
        minimum_similarity=minimum_similarity,
        minimum_shared_tags=minimum_shared_tags,
    )

    # Works without a usable date are exported as roots so the forest still
    # contains every catalogued work.
    dated_ids = {record.entity_id for record in records}
    undated_rows = db.execute(
        """
        select entity_id
        from entities
        where is_catalogued = 1 and (release_date is null or release_date = '')
        order by entity_id
        """
    ).fetchall()

    nodes = [
        {
            "id": record.entity_id,
            "parent": record.parent_id,
            "score": record.score,
            "shared": record.shared_tags,
            "topTags": list(record.top_tags),
        }
        for record in records
    ]
    for row in undated_rows:
        entity_id = int(row["entity_id"])
        if entity_id in dated_ids:
            continue
        nodes.append({"id": entity_id, "parent": None, "score": 0.0, "shared": 0, "topTags": []})

    nodes.sort(key=lambda node: node["id"])
    return {"version": 1, "note": EVOLUTION_NOTE, "nodes": nodes}
