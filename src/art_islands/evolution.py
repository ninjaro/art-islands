"""Build-time inferred lineage ("Evolution") calculation.

The result is an inferred temporal similarity structure, not proven
historical influence. Every edge stores the evidence supporting it
(similarity score, shared feature count, strongest contributing factors with
human-readable labels) so the UI can explain it without claiming factual
influence.

Hard invariants:

* a parent is strictly earlier than its child;
* a node has zero or one parent;
* no self-parent and no cycles (guaranteed by strict date ordering);
* only work entities become nodes — people, groups, and organizations may
  only influence similarity through one-hop derived features;
* no fabricated entity ids;
* deterministic results for identical inputs.

Scoring uses the shared feature model (docs/feature-model.md, features.py):
direct concepts, contributor-derived features with role multipliers, and
content-guide (advisory) features, all weighted, polarity-aware, and
IDF-scaled. Candidate generation is bounded through a feature-to-entity index
over earlier works instead of a quadratic all-pairs comparison; extremely
common features are downweighted by IDF and skipped entirely for candidate
generation.

When the database only contains the legacy schema (no V2 tables), features
fall back to legacy tags — the documented compatibility adapter for migrated
legacy-only databases.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from . import features as features_module
from .features import CANDIDATE_FEATURE_DF_CAP, Feature
from .model import DEFAULT_SETTINGS

EVOLUTION_NOTE = (
    "Branches are inferred from date and feature similarity. "
    "They do not prove direct influence."
)

EVOLUTION_EXPORT_VERSION = 2

# Preference multiplier applied to candidates of a different broad work kind
# (configurable via settings.evolution.kindMismatchFactor).
DEFAULT_KIND_MISMATCH_FACTOR = 0.6

# Mild temporal-distance penalty half-life, in years. Long historical
# branches stay possible: a 75-year gap halves the ranking score.
TEMPORAL_HALF_LIFE_YEARS = 75.0

TOP_FACTORS = 3

BROAD_KIND_BY_TYPE = {
    "film": "film",
    "television_series": "tv",
    "music_album": "music",
    "musical_work": "music",
    "video_game": "game",
}

LEGACY_BROAD_KIND_BY_ENTITY_KIND = {1: "film", 2: "music", 6: "game"}


@dataclass(frozen=True)
class LineageWork:
    entity_id: int
    kind: str
    date: str
    year: int
    features: dict[str, Feature] = field(default_factory=dict)


@dataclass(frozen=True)
class LineageRecord:
    entity_id: int
    parent_id: int | None
    score: float
    shared_features: int
    top_factors: tuple[dict[str, Any], ...]


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?", (name,)
    ).fetchone()
    return row is not None


def _v2_broad_kinds(db: sqlite3.Connection) -> dict[int, str]:
    kinds: dict[int, str] = {}
    for row in db.execute(
        """
        select et.entity_id, d.code
        from entity_types et
        join entity_type_definitions d on d.entity_type_id = et.entity_type_id
        where et.is_primary = 1
        order by et.entity_id, et.entity_type_id
        """
    ):
        kinds.setdefault(int(row["entity_id"]), BROAD_KIND_BY_TYPE.get(row["code"], "work"))
    return kinds


def _v2_features_by_entity(
    db: sqlite3.Connection,
    feature_settings: dict[str, float],
) -> dict[int, dict[str, Feature]]:
    concepts: defaultdict[int, list[tuple]] = defaultdict(list)
    for row in db.execute(
        """
        select ec.entity_id, ec.concept_id, c.label, cc.label as category_label,
               ec.weight, ec.polarity
        from entity_concepts ec
        join concepts c on c.concept_id = ec.concept_id
        join concept_categories cc on cc.concept_category_id = c.concept_category_id
        order by ec.entity_id, ec.concept_id
        """
    ):
        concepts[int(row["entity_id"])].append(
            (int(row["concept_id"]), row["label"], row["category_label"], int(row["weight"]), int(row["polarity"]))
        )

    contributors: defaultdict[int, list[tuple]] = defaultdict(list)
    for row in db.execute(
        """
        select r.source_entity_id, r.target_entity_id, e.label, e.entity_family,
               t.code, r.weight, r.polarity
        from entity_relations r
        join relation_types t on t.relation_type_id = r.relation_type_id
        join entities e on e.entity_id = r.target_entity_id
        order by r.source_entity_id, t.code, r.target_entity_id
        """
    ):
        contributors[int(row["source_entity_id"])].append(
            (
                int(row["target_entity_id"]),
                row["label"],
                row["entity_family"],
                row["code"],
                int(row["weight"]),
                int(row["polarity"]),
            )
        )

    advisories: defaultdict[int, list[tuple]] = defaultdict(list)
    for row in db.execute(
        """
        select a.entity_id, a.advisory_category_id, c.label, a.intensity
        from entity_advisories a
        join advisory_categories c on c.advisory_category_id = a.advisory_category_id
        order by a.entity_id, a.advisory_category_id
        """
    ):
        advisories[int(row["entity_id"])].append(
            (int(row["advisory_category_id"]), row["label"], row["intensity"])
        )

    entity_ids = set(concepts) | set(contributors) | set(advisories)
    return {
        entity_id: features_module.extract_features(
            concepts.get(entity_id, ()),
            contributors.get(entity_id, ()),
            advisories.get(entity_id, ()),
            feature_settings,
        )
        for entity_id in entity_ids
    }


def _legacy_features_by_entity(
    db: sqlite3.Connection,
    feature_settings: dict[str, float],
) -> dict[int, dict[str, Feature]]:
    """Compatibility adapter for legacy-only databases: tags become direct
    concept features (concept ids reuse legacy tag ids)."""

    tag_rows: defaultdict[int, list[tuple]] = defaultdict(list)
    for row in db.execute(
        """
        select et.entity_id, et.tag_id, t.name, et.weight, et.polarity
        from entity_tags et
        join tags t on t.tag_id = et.tag_id
        order by et.entity_id, et.tag_id
        """
    ):
        tag_rows[int(row["entity_id"])].append(
            (int(row["tag_id"]), row["name"], "Concept", int(row["weight"]), int(row["polarity"]))
        )
    return {
        entity_id: features_module.extract_features(rows, (), (), feature_settings)
        for entity_id, rows in tag_rows.items()
    }


def load_catalogued_works(
    db: sqlite3.Connection,
    feature_settings: dict[str, float] | None = None,
) -> list[LineageWork]:
    if feature_settings is None:
        feature_settings = dict(DEFAULT_SETTINGS["features"])

    has_v2 = _has_table(db, "entity_concepts")
    if has_v2:
        rows = db.execute(
            """
            select entity_id, release_date
            from entities
            where is_catalogued = 1 and entity_family = 'work'
            order by entity_id
            """
        ).fetchall()
        kinds = _v2_broad_kinds(db)
        features_by_entity = _v2_features_by_entity(db, feature_settings)
    else:
        rows = db.execute(
            """
            select entity_id, entity_kind, release_date
            from entities
            where is_catalogued = 1
            order by entity_id
            """
        ).fetchall()
        kinds = {
            int(row["entity_id"]): LEGACY_BROAD_KIND_BY_ENTITY_KIND.get(int(row["entity_kind"]), "work")
            for row in rows
        }
        features_by_entity = _legacy_features_by_entity(db, feature_settings)

    works: list[LineageWork] = []
    for row in rows:
        date = row["release_date"]
        if not date:
            continue  # undated works cannot be ordered; they become roots
        entity_id = int(row["entity_id"])
        works.append(
            LineageWork(
                entity_id=entity_id,
                kind=kinds.get(entity_id, "work"),
                date=str(date),
                year=int(str(date)[:4]),
                features=features_by_entity.get(entity_id, {}),
            )
        )
    return works


def compute_lineage(
    works: list[LineageWork],
    *,
    minimum_similarity: float,
    minimum_shared_features: int,
    kind_mismatch_factor: float = DEFAULT_KIND_MISMATCH_FACTOR,
    candidate_df_cap: int = CANDIDATE_FEATURE_DF_CAP,
) -> list[LineageRecord]:
    """Assign at most one strictly-earlier parent per work."""

    base = {work.entity_id: work.features for work in works}
    index = features_module.build_feature_index(base)

    ordered = sorted(works, key=lambda work: (work.date, work.entity_id))

    # Postings over strictly earlier works only. Works sharing the same date
    # are added after the whole date group is processed, so a parent is
    # always strictly earlier than its child.
    postings: defaultdict[str, list[int]] = defaultdict(list)
    processed: dict[int, LineageWork] = {}
    records: list[LineageRecord] = []

    position = 0
    while position < len(ordered):
        group_end = position
        current_date = ordered[position].date
        while group_end < len(ordered) and ordered[group_end].date == current_date:
            group_end += 1
        group = ordered[position:group_end]

        for work in group:
            records.append(
                _best_parent(
                    work,
                    postings=postings,
                    processed=processed,
                    index=index,
                    candidate_df_cap=candidate_df_cap,
                    minimum_similarity=minimum_similarity,
                    minimum_shared_features=minimum_shared_features,
                    kind_mismatch_factor=kind_mismatch_factor,
                )
            )

        for work in group:
            processed[work.entity_id] = work
            for key in index.vectors.get(work.entity_id, ()):  # final keys only
                if index.document_frequency.get(key, 0) <= candidate_df_cap:
                    postings[key].append(work.entity_id)

        position = group_end

    records.sort(key=lambda record: record.entity_id)
    return records


def _best_parent(
    work: LineageWork,
    *,
    postings: dict[str, list[int]],
    processed: dict[int, LineageWork],
    index: features_module.FeatureIndex,
    candidate_df_cap: int,
    minimum_similarity: float,
    minimum_shared_features: int,
    kind_mismatch_factor: float,
) -> LineageRecord:
    vector = index.vectors.get(work.entity_id, {})
    norm = index.norms.get(work.entity_id, 0.0)
    if not vector or norm == 0:
        return LineageRecord(work.entity_id, None, 0.0, 0, ())

    candidates: set[int] = set()
    for key in vector:
        if index.document_frequency.get(key, 0) > candidate_df_cap:
            continue
        candidates.update(postings.get(key, ()))

    best: tuple[float, float, str, int] | None = None  # (adjusted, raw, date, id)
    best_shared: list[tuple[float, str]] = []

    for candidate_id in sorted(candidates):
        other = processed[candidate_id]
        other_vector = index.vectors.get(candidate_id, {})
        other_norm = index.norms.get(candidate_id, 0.0)
        if other_norm == 0:
            continue

        small, large = (
            (vector, other_vector) if len(vector) <= len(other_vector) else (other_vector, vector)
        )
        dot = 0.0
        shared: list[tuple[float, str]] = []
        for key, value in small.items():
            other_value = large.get(key)
            if other_value is None:
                continue
            contribution = value * other_value
            dot += contribution
            shared.append((contribution, key))

        if len(shared) < minimum_shared_features:
            continue
        similarity = dot / (norm * other_norm)
        if similarity <= 0 or similarity < minimum_similarity:
            continue

        kind_factor = 1.0 if other.kind == work.kind else kind_mismatch_factor
        years = max(0, work.year - other.year)
        temporal_factor = 1.0 / (1.0 + years / TEMPORAL_HALF_LIFE_YEARS)
        adjusted = similarity * kind_factor * temporal_factor

        # Deterministic tie-breaks: stronger adjusted score, then later
        # (closer) parent date, then smaller entity id.
        key_tuple = (adjusted, similarity, other.date, -candidate_id)
        if best is None or key_tuple > (best[0], best[1], best[2], -best[3]):
            best = (adjusted, similarity, other.date, candidate_id)
            best_shared = shared

    if best is None:
        return LineageRecord(work.entity_id, None, 0.0, 0, ())

    best_shared.sort(key=lambda entry: (-entry[0], entry[1]))
    meta = index.features_by_id.get(work.entity_id, {})
    top_factors = tuple(
        features_module.factor_dict(
            meta.get(key, Feature(key, key, 0.0, "direct-concept")),
            round(contribution, 6),
        )
        for contribution, key in best_shared[:TOP_FACTORS]
    )
    return LineageRecord(
        entity_id=work.entity_id,
        parent_id=best[3],
        score=round(best[1], 4),
        shared_features=len(best_shared),
        top_factors=top_factors,
    )


def build_evolution_export(
    db: sqlite3.Connection,
    settings: dict[str, Any],
) -> dict[str, Any]:
    evolution_settings = settings.get("evolution", {})
    minimum_similarity = float(evolution_settings.get("minimumSimilarity", 0.18))
    minimum_shared_features = int(
        evolution_settings.get("minimumSharedFeatures", evolution_settings.get("minimumSharedTags", 2))
    )
    kind_mismatch_factor = float(
        evolution_settings.get("kindMismatchFactor", DEFAULT_KIND_MISMATCH_FACTOR)
    )
    feature_settings = {
        **DEFAULT_SETTINGS["features"],
        **{k: float(v) for k, v in settings.get("features", {}).items()},
    }

    works = load_catalogued_works(db, feature_settings)
    records = compute_lineage(
        works,
        minimum_similarity=minimum_similarity,
        minimum_shared_features=minimum_shared_features,
        kind_mismatch_factor=kind_mismatch_factor,
    )

    # Works without a usable date are exported as roots so the forest still
    # contains every catalogued work.
    dated_ids = {record.entity_id for record in records}
    family_filter = "and entity_family = 'work'" if _has_table(db, "entity_concepts") else ""
    undated_rows = db.execute(
        f"""
        select entity_id
        from entities
        where is_catalogued = 1 {family_filter}
          and (release_date is null or release_date = '')
        order by entity_id
        """
    ).fetchall()

    nodes = [
        {
            "id": record.entity_id,
            "parent": record.parent_id,
            "evidence": {
                "score": record.score,
                "sharedFeatureCount": record.shared_features,
                "topFactors": list(record.top_factors),
            },
        }
        for record in records
    ]
    for row in undated_rows:
        entity_id = int(row["entity_id"])
        if entity_id in dated_ids:
            continue
        nodes.append(
            {
                "id": entity_id,
                "parent": None,
                "evidence": {"score": 0.0, "sharedFeatureCount": 0, "topFactors": []},
            }
        )

    nodes.sort(key=lambda node: node["id"])
    return {"version": EVOLUTION_EXPORT_VERSION, "note": EVOLUTION_NOTE, "nodes": nodes}
