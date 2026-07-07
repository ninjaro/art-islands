from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .model import (
    REF_KIND_DISCOGS,
    REF_KIND_IMDB,
    REF_KIND_MUSICBRAINZ,
    REF_KIND_TMDB,
    REF_KIND_WIKIDATA,
    load_settings,
    write_json,
)


REQUIRED_V2_TABLES = (
    "entities",
    "entity_refs",
    "tags",
    "entity_tags",
    "entity_links",
    "entity_tag_refs",
    "entity_link_refs",
    "data_sources",
    "source_records",
    "identifier_schemes",
    "entity_identifiers",
    "entity_type_definitions",
    "entity_types",
    "entity_texts",
    "relation_types",
    "entity_relations",
    "concept_categories",
    "concepts",
    "entity_concepts",
    "entity_dates",
    "measurement_types",
    "entity_measurements",
    "advisory_categories",
    "entity_advisories",
    "age_rating_systems",
    "entity_age_ratings",
    "entity_restrictions",
    "patch_references",
    "content_guide_categories",
    "entity_content_guide_dimensions",
)


def export_v2_static_data(
    db_path: Path,
    output_dir: Path,
    settings_path: Path | None = None,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        check = db.execute("pragma quick_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"database failed quick_check: {check}")
        catalog_ids = {
            int(row["entity_id"])
            for row in db.execute("select entity_id from entities where is_catalogued = 1")
        }
        exported_entity_ids = referenced_export_entity_ids(db, catalog_ids)
        entities = export_v2_entities(db, exported_entity_ids)
        catalog = export_v2_catalog(db, catalog_ids)
        entity_types = export_v2_entity_types(db, exported_entity_ids)
        relations = export_v2_relations(db, catalog_ids, exported_entity_ids)
        concepts = export_v2_concepts(db, catalog_ids)
        advisories = export_v2_advisories(db, catalog_ids)
        ratings = export_v2_age_ratings(db, catalog_ids)
        restrictions = export_v2_restrictions(db, catalog_ids)
        settings = load_settings(settings_path)
    finally:
        db.close()

    write_json(output_dir / "catalog.json", catalog)
    write_json(output_dir / "entities.json", entities)
    write_json(output_dir / "entity-types.json", entity_types)
    write_json(output_dir / "relations.json", relations)
    write_json(output_dir / "concepts.json", concepts)
    write_json(output_dir / "advisories.json", advisories)
    write_json(output_dir / "ratings.json", ratings)
    write_json(output_dir / "restrictions.json", restrictions)
    write_json(output_dir / "settings.json", settings)
    return {
        "catalog": len(catalog),
        "entities": len(entities),
        "relations": len(relations),
        "concepts": len(concepts["concepts"]),
        "entity_concepts": len(concepts["entityConcepts"]),
    }


def placeholders(values: Iterable[Any]) -> str:
    values = tuple(values)
    return ",".join("?" for _ in values) if values else "null"


def referenced_export_entity_ids(db: sqlite3.Connection, catalog_ids: set[int]) -> set[int]:
    exported = set(catalog_ids)
    if catalog_ids:
        for row in db.execute(
            """
            select target_entity_id
            from entity_relations
            where source_entity_id in (%s)
            """
            % placeholders(catalog_ids),
            tuple(catalog_ids),
        ):
            exported.add(int(row["target_entity_id"]))
    return exported


def export_v2_entities(db: sqlite3.Connection, entity_ids: set[int]) -> dict[str, Any]:
    if not entity_ids:
        return {}
    rows = rows_as_dicts(
        db.execute(
            """
            select entity_id as id, label, short_description as description,
                   entity_family as family, image_ref as image,
                   is_catalogued as catalogued
            from entities
            where entity_id in (%s)
            order by entity_id
            """
            % placeholders(entity_ids),
            tuple(entity_ids),
        )
    )
    identifiers = grouped_rows(
        db.execute(
            """
            select i.entity_id, s.code, i.value, i.is_primary
            from entity_identifiers i
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            where i.entity_id in (%s)
            order by i.entity_id, s.code, i.value
            """
            % placeholders(entity_ids),
            tuple(entity_ids),
        ),
        "entity_id",
        lambda row: {"scheme": row["code"], "value": row["value"], "primary": bool(row["is_primary"])},
    )
    result = {}
    for row in rows:
        entity = {
            key: value
            for key, value in row.items()
            if value is not None and key != "catalogued"
        }
        entity["catalogued"] = bool(row["catalogued"])
        if identifiers.get(row["id"]):
            entity["identifiers"] = identifiers[row["id"]]
        result[str(row["id"])] = entity
    return result


def export_v2_catalog(db: sqlite3.Connection, catalog_ids: set[int]) -> list[dict[str, Any]]:
    rows = rows_as_dicts(
        db.execute(
            """
            select entity_id as id, label, entity_family as family, image_ref as image,
                   release_date as compatibilityDate, date_precision as compatibilityDatePrecision
            from entities
            where is_catalogued = 1
            order by
              case when release_date is null then 1 else 0 end,
              release_date,
              label collate nocase,
              entity_id
            """
        )
    )
    dates = export_v2_dates_by_entity(db, catalog_ids)
    contributors = export_v2_contributors_by_entity(db, catalog_ids)
    concept_groups = export_v2_concept_groups_by_entity(db, catalog_ids)
    measurements = export_v2_measurements_by_entity(db, catalog_ids)
    output = []
    for row in rows:
        item = {key: value for key, value in row.items() if value is not None}
        entity_id = int(row["id"])
        if dates.get(entity_id):
            item["dates"] = dates[entity_id]
        if contributors.get(entity_id):
            item["contributors"] = contributors[entity_id]
        if concept_groups.get(entity_id):
            item["concepts"] = concept_groups[entity_id]
        if measurements.get(entity_id):
            item["measurements"] = measurements[entity_id]
        output.append(item)
    return output


def export_v2_entity_types(db: sqlite3.Connection, entity_ids: set[int]) -> dict[str, Any]:
    definitions = rows_as_dicts(
        db.execute(
            """
            select entity_type_id as id, code, family, label, description
            from entity_type_definitions
            order by code
            """
        )
    )
    assignments = (
        rows_as_dicts(
            db.execute(
                """
                select entity_id as entityId, entity_type_id as typeId,
                       is_primary as isPrimary, confidence
                from entity_types
                where entity_id in (%s)
                order by entity_id, entity_type_id
                """
                % placeholders(entity_ids),
                tuple(entity_ids),
            )
        )
        if entity_ids
        else []
    )
    return {"definitions": definitions, "assignments": assignments}


def export_v2_dates_by_entity(db: sqlite3.Connection, entity_ids: set[int]) -> dict[int, list[dict[str, Any]]]:
    if not entity_ids:
        return {}
    return grouped_rows(
        db.execute(
            """
            select entity_id, date_type, date_value, date_precision,
                   end_date_value, end_date_precision, edition_label,
                   rank, is_primary, confidence
            from entity_dates
            where entity_id in (%s)
            order by entity_id, is_primary desc, date_type, date_value
            """
            % placeholders(entity_ids),
            tuple(entity_ids),
        ),
        "entity_id",
        lambda row: compact_dict(
            {
                "type": row["date_type"],
                "value": row["date_value"],
                "precision": row["date_precision"],
                "endValue": row["end_date_value"],
                "endPrecision": row["end_date_precision"],
                "edition": row["edition_label"],
                "rank": row["rank"],
                "primary": bool(row["is_primary"]),
                "confidence": row["confidence"],
            }
        ),
    )


def export_v2_contributors_by_entity(db: sqlite3.Connection, entity_ids: set[int]) -> dict[int, dict[str, list[int]]]:
    if not entity_ids:
        return {}
    result: dict[int, dict[str, list[int]]] = {}
    for row in db.execute(
        """
        select r.source_entity_id, r.target_entity_id, t.code
        from entity_relations r
        join relation_types t on t.relation_type_id = r.relation_type_id
        where r.source_entity_id in (%s)
        order by r.source_entity_id, t.code, r.target_entity_id
        """
        % placeholders(entity_ids),
        tuple(entity_ids),
    ):
        result.setdefault(int(row["source_entity_id"]), {}).setdefault(row["code"], []).append(
            int(row["target_entity_id"])
        )
    return result


def export_v2_concept_groups_by_entity(db: sqlite3.Connection, entity_ids: set[int]) -> dict[int, dict[str, list[int]]]:
    if not entity_ids:
        return {}
    result: dict[int, dict[str, list[int]]] = {}
    for row in db.execute(
        """
        select ec.entity_id, ec.concept_id, cc.code
        from entity_concepts ec
        join concepts c on c.concept_id = ec.concept_id
        join concept_categories cc on cc.concept_category_id = c.concept_category_id
        where ec.entity_id in (%s)
        order by ec.entity_id, cc.code, ec.weight desc, c.label
        """
        % placeholders(entity_ids),
        tuple(entity_ids),
    ):
        result.setdefault(int(row["entity_id"]), {}).setdefault(row["code"], []).append(int(row["concept_id"]))
    return result


def export_v2_measurements_by_entity(db: sqlite3.Connection, entity_ids: set[int]) -> dict[int, list[dict[str, Any]]]:
    if not entity_ids:
        return {}
    return grouped_rows(
        db.execute(
            """
            select m.entity_id, t.code, m.numeric_value, m.text_value,
                   m.unit, m.qualifier, m.confidence
            from entity_measurements m
            join measurement_types t on t.measurement_type_id = m.measurement_type_id
            where m.entity_id in (%s)
            order by m.entity_id, t.code
            """
            % placeholders(entity_ids),
            tuple(entity_ids),
        ),
        "entity_id",
        lambda row: compact_dict(
            {
                "type": row["code"],
                "number": row["numeric_value"],
                "text": row["text_value"],
                "unit": row["unit"],
                "qualifier": row["qualifier"],
                "confidence": row["confidence"],
            }
        ),
    )


def export_v2_relations(
    db: sqlite3.Connection,
    catalog_ids: set[int],
    exported_entity_ids: set[int],
) -> list[dict[str, Any]]:
    if not catalog_ids:
        return []
    return [
        compact_dict(
            {
                "id": row["entity_relation_id"],
                "source": row["source_entity_id"],
                "target": row["target_entity_id"],
                "type": row["code"],
                "roleLabel": row["role_label"],
                "characterLabel": row["character_label"],
                "weight": row["weight"],
                "polarity": row["polarity"],
                "confidence": row["confidence"],
            }
        )
        for row in db.execute(
            """
            select r.*, t.code
            from entity_relations r
            join relation_types t on t.relation_type_id = r.relation_type_id
            where r.source_entity_id in (%s)
              and r.target_entity_id in (%s)
            order by r.source_entity_id, t.code, r.target_entity_id
            """
            % (placeholders(catalog_ids), placeholders(exported_entity_ids)),
            tuple(catalog_ids) + tuple(exported_entity_ids),
        )
    ]


def export_v2_concepts(db: sqlite3.Connection, catalog_ids: set[int]) -> dict[str, Any]:
    categories = rows_as_dicts(
        db.execute(
            """
            select concept_category_id as id, code, label
            from concept_categories
            order by code
            """
        )
    )
    concept_rows = rows_as_dicts(
        db.execute(
            """
            select c.concept_id as id, c.label, c.description,
                   cc.code as category, c.namespace, c.value,
                   c.legacy_tag_id as legacyTagId,
                   c.classification_rule as classificationRule,
                   c.confidence, c.review_recommended as reviewRecommended
            from concepts c
            join concept_categories cc on cc.concept_category_id = c.concept_category_id
            order by cc.code, c.label
            """
        )
    )
    entity_concepts = (
        rows_as_dicts(
            db.execute(
                """
                select ec.entity_id as entityId, ec.concept_id as conceptId,
                       ec.weight, ec.polarity, ec.confidence
                from entity_concepts ec
                where ec.entity_id in (%s)
                order by ec.entity_id, ec.weight desc, ec.concept_id
                """
                % placeholders(catalog_ids),
                tuple(catalog_ids),
            )
        )
        if catalog_ids
        else []
    )
    return {
        "categories": categories,
        "concepts": [compact_dict(row) for row in concept_rows],
        "entityConcepts": entity_concepts,
    }


def export_v2_advisories(db: sqlite3.Connection, catalog_ids: set[int]) -> dict[str, Any]:
    categories = rows_as_dicts(
        db.execute(
            """
            select advisory_category_id as id, code, label
            from advisory_categories
            order by code
            """
        )
    )
    advisories = (
        rows_as_dicts(
            db.execute(
                """
                select entity_advisory_id as id, entity_id as entityId,
                       advisory_category_id as categoryId, concept_id as conceptId,
                       severity, intensity, uncertainty
                from entity_advisories
                where entity_id in (%s)
                order by entity_id, advisory_category_id
                """
                % placeholders(catalog_ids),
                tuple(catalog_ids),
            )
        )
        if catalog_ids
        else []
    )
    return {"categories": categories, "advisories": advisories}


def export_v2_age_ratings(db: sqlite3.Connection, catalog_ids: set[int]) -> dict[str, Any]:
    systems = rows_as_dicts(
        db.execute(
            """
            select age_rating_system_id as id, code, country_code as countryCode, label
            from age_rating_systems
            order by code
            """
        )
    )
    ratings = (
        rows_as_dicts(
            db.execute(
                """
                select entity_age_rating_id as id, entity_id as entityId,
                       age_rating_system_id as systemId, certificate,
                       minimum_age as minimumAge, edition_label as editionLabel,
                       descriptors_json as descriptorsJson, rating_date as ratingDate
                from entity_age_ratings
                where entity_id in (%s)
                order by entity_id, age_rating_system_id, certificate
                """
                % placeholders(catalog_ids),
                tuple(catalog_ids),
            )
        )
        if catalog_ids
        else []
    )
    return {"systems": systems, "ratings": ratings}


def export_v2_restrictions(db: sqlite3.Connection, catalog_ids: set[int]) -> list[dict[str, Any]]:
    if not catalog_ids:
        return []
    return rows_as_dicts(
        db.execute(
            """
            select entity_restriction_id as id, entity_id as entityId,
                   country_code as countryCode, region_label as regionLabel,
                   restriction_type as restrictionType, start_date as startDate,
                   end_date as endDate, reason, edition_label as editionLabel, status
            from entity_restrictions
            where entity_id in (%s)
            order by entity_id, country_code, restriction_type
            """
            % placeholders(catalog_ids),
            tuple(catalog_ids),
        )
    )


def validate_v2_database(project_root: Path, source_db: Path, v2_db: Path) -> dict[str, Any]:
    del project_root
    source = sqlite3.connect(source_db)
    target = sqlite3.connect(v2_db)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
    try:
        missing_tables = missing_required_tables(target)
        source_catalog_qids = catalog_qids(source)
        target_catalog_qids = catalog_qids_v2(target)
        tag_mismatches = legacy_tag_mismatches(target) if not missing_tables else 0
        source_identifier_pairs = source_ref_identifier_pairs(source)
        target_identifier_pairs = v2_identifier_pairs(target)
        missing_source_identifiers = sorted(source_identifier_pairs - target_identifier_pairs)
        orphan_counts = logical_orphan_counts(target)
        source_fk = [list(row) for row in source.execute("pragma foreign_key_check")]
        target_fk = [list(row) for row in target.execute("pragma foreign_key_check")]
        summary = {
            "source": str(source_db),
            "v2": str(v2_db),
            "sourceIntegrity": source.execute("pragma integrity_check").fetchone()[0],
            "v2Integrity": target.execute("pragma integrity_check").fetchone()[0],
            "sourceForeignKeys": source_fk,
            "v2ForeignKeys": target_fk,
            "requiredTables": {"missing": missing_tables},
            "catalogQids": {
                "source": len(source_catalog_qids),
                "v2": len(target_catalog_qids),
                "missingInV2": sorted(source_catalog_qids - target_catalog_qids)[:100],
                "extraInV2": sorted(target_catalog_qids - source_catalog_qids)[:100],
            },
            "manualTagWeightPolarityMismatches": int(tag_mismatches),
            "externalIdentifiers": {
                "sourceRefs": len(source_identifier_pairs),
                "v2Identifiers": table_count(target, "entity_identifiers"),
                "sourceRefsPreserved": not missing_source_identifiers,
                "missingSourceRefs": [
                    {"scheme": scheme, "value": value}
                    for scheme, value in missing_source_identifiers[:100]
                ],
            },
            "logicalSourceOrphans": orphan_counts,
            "counts": validation_counts(target),
        }
        summary["ok"] = (
            summary["sourceIntegrity"] == "ok"
            and summary["v2Integrity"] == "ok"
            and not summary["sourceForeignKeys"]
            and not summary["v2ForeignKeys"]
            and not missing_tables
            and not summary["catalogQids"]["missingInV2"]
            and tag_mismatches == 0
            and not missing_source_identifiers
            and not any(orphan_counts.values())
        )
        return summary
    finally:
        target.close()
        source.close()


def missing_required_tables(db: sqlite3.Connection) -> list[str]:
    existing = {
        row["name"]
        for row in db.execute("select name from sqlite_master where type = 'table'")
    }
    return sorted(set(REQUIRED_V2_TABLES) - existing)


def legacy_tag_mismatches(db: sqlite3.Connection) -> int:
    return int(
        db.execute(
            """
            select count(*)
            from entity_tags et
            left join concepts c on c.legacy_tag_id = et.tag_id
            left join entity_concepts ec
              on ec.entity_id = et.entity_id and ec.concept_id = c.concept_id
            where ec.entity_id is null
               or ec.weight <> et.weight
               or ec.polarity <> et.polarity
            """
        ).fetchone()[0]
    )


def logical_orphan_counts(db: sqlite3.Connection) -> dict[str, int]:
    checks = {
        "entityTagRefs": """
            select count(*) from entity_tag_refs
            where ref_id not in (select source_record_id from source_records)
        """,
        "entityLinkRefs": """
            select count(*) from entity_link_refs
            where ref_id not in (select source_record_id from source_records)
        """,
        "entityIdentifiers": """
            select count(*) from entity_identifiers
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityTypes": """
            select count(*) from entity_types
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityTexts": """
            select count(*) from entity_texts
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityRelations": """
            select count(*) from entity_relations
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityConcepts": """
            select count(*) from entity_concepts
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityDates": """
            select count(*) from entity_dates
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityMeasurements": """
            select count(*) from entity_measurements
            where source_record_id is not null
              and source_record_id not in (select source_record_id from source_records)
        """,
        "entityConceptPatchRefs": """
            select count(*) from entity_concept_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entityConceptSourceRefs": """
            select count(*) from entity_concept_source_refs
            where source_record_id not in (select source_record_id from source_records)
        """,
        "entityContentGuidePatchRefs": """
            select count(*) from entity_content_guide_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entityContentGuideSourceRefs": """
            select count(*) from entity_content_guide_source_refs
            where source_record_id not in (select source_record_id from source_records)
        """,
        "entityAdvisoryPatchRefs": """
            select count(*) from entity_advisory_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entityAgeRatingPatchRefs": """
            select count(*) from entity_age_rating_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entityRestrictionPatchRefs": """
            select count(*) from entity_restriction_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
    }
    return {name: int(db.execute(sql).fetchone()[0]) for name, sql in checks.items()}


def validation_counts(db: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "entities",
        "entity_refs",
        "entity_identifiers",
        "entity_relations",
        "entity_measurements",
        "tags",
        "entity_tags",
        "concepts",
        "entity_concepts",
        "entity_content_guide_dimensions",
        "entity_advisories",
        "entity_age_ratings",
        "entity_restrictions",
        "source_records",
        "patch_references",
    )
    counts = {table: table_count(db, table) for table in tables}
    counts["catalogued_entities"] = int(
        db.execute("select count(*) from entities where is_catalogued = 1").fetchone()[0]
    )
    return counts


def catalog_qids(db: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in db.execute(
            """
            select r.ref_value
            from entity_refs r
            join entities e on e.entity_id = r.entity_id
            where e.is_catalogued = 1 and r.ref_kind = ?
            """,
            (REF_KIND_WIKIDATA,),
        )
    }


def catalog_qids_v2(db: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in db.execute(
            """
            select i.value
            from entity_identifiers i
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            join entities e on e.entity_id = i.entity_id
            where e.is_catalogued = 1 and s.code = 'wikidata'
            """
        )
    }


def source_ref_identifier_pairs(db: sqlite3.Connection) -> set[tuple[str, str]]:
    kind_to_scheme = {
        REF_KIND_WIKIDATA: "wikidata",
        REF_KIND_IMDB: "imdb_title",
        REF_KIND_TMDB: "tmdb_movie",
        REF_KIND_MUSICBRAINZ: "musicbrainz_release_group",
        REF_KIND_DISCOGS: "discogs_release",
    }
    pairs = set()
    for row in db.execute("select ref_kind, ref_value from entity_refs order by ref_kind, ref_value"):
        scheme = kind_to_scheme.get(int(row["ref_kind"]))
        if scheme:
            pairs.add((scheme, row["ref_value"]))
    return pairs


def v2_identifier_pairs(db: sqlite3.Connection) -> set[tuple[str, str]]:
    return {
        (row["code"], row["value"])
        for row in db.execute(
            """
            select s.code, i.value
            from entity_identifiers i
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            order by s.code, i.value
            """
        )
    }


def table_count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"select count(*) from {table}").fetchone()[0])


def grouped_rows(rows: Iterable[sqlite3.Row], key: str, transform) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = {}
    for row in rows:
        grouped.setdefault(int(row[key]), []).append(transform(row))
    return grouped


def rows_as_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
