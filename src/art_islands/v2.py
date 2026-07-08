from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .model import (
    load_settings,
    write_json,
)


REQUIRED_V2_TABLES = (
    "entities",
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
    "entity_concept_references",
    "entity_dates",
    "measurement_types",
    "entity_measurements",
    "entity_restrictions",
    "entity_restriction_references",
    "source_references",
    "content_guide_categories",
    "entity_content_guide_dimensions",
    "entity_content_guide_references",
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
    write_json(output_dir / "restrictions.json", restrictions)
    write_json(output_dir / "settings.json", settings)
    stale_ratings = output_dir / "ratings.json"
    if stale_ratings.exists():
        stale_ratings.unlink()
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
            select m.entity_id, t.code, m.numeric_value, m.unit, m.confidence
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
                "unit": row["unit"],
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
                "weight": row["weight"],
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
                   c.confidence
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
                order by ec.entity_id, ec.weight is null, ec.weight desc, ec.concept_id
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
            select category_code as code, label, description
            from content_guide_categories
            order by code
            """
        )
    )
    advisories = (
        rows_as_dicts(
            db.execute(
                """
                select entity_id as entityId, category_code as categoryCode,
                       scale_version as scaleVersion, medium, intensity,
                       centrality, explicitness, realism, recurrence,
                       sensory_impact as sensoryImpact, coercion,
                       avoidance_priority as avoidancePriority,
                       narrative_proximity as narrativeProximity,
                       language_dependency as languageDependency,
                       guidance_level as guidanceLevel,
                       content_role as contentRole, stance,
                       genre_context as genreContext, confidence,
                       uncertainty, description,
                       dimension_values_json as dimensionValuesJson,
                       context_json as contextJson
                from entity_content_guide_dimensions
                where entity_id in (%s)
                order by entity_id, category_code
                """
                % placeholders(catalog_ids),
                tuple(catalog_ids),
            )
        )
        if catalog_ids
        else []
    )
    return {"categories": categories, "advisories": [compact_dict(row) for row in advisories]}


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
        source_catalog_qids = catalog_qids_v2(source) if not missing_required_tables(source) else set()
        target_catalog_qids = catalog_qids_v2(target)
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
            "externalIdentifiers": {
                "v2Identifiers": table_count(target, "entity_identifiers"),
                "catalogWikidataIdentifiers": len(target_catalog_qids),
            },
            "logicalReferenceOrphans": orphan_counts,
            "counts": validation_counts(target),
        }
        summary["ok"] = (
            summary["sourceIntegrity"] == "ok"
            and summary["v2Integrity"] == "ok"
            and not summary["sourceForeignKeys"]
            and not summary["v2ForeignKeys"]
            and not missing_tables
            and not summary["catalogQids"]["missingInV2"]
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


def logical_orphan_counts(db: sqlite3.Connection) -> dict[str, int]:
    checks = {
        "entityConceptReferences": """
            select count(*) from entity_concept_references
            where reference_id not in (select reference_id from source_references)
        """,
        "entityContentGuideReferences": """
            select count(*) from entity_content_guide_references
            where reference_id not in (select reference_id from source_references)
        """,
        "entityRestrictionReferences": """
            select count(*) from entity_restriction_references
            where reference_id not in (select reference_id from source_references)
        """,
    }
    return {name: int(db.execute(sql).fetchone()[0]) for name, sql in checks.items()}


def validation_counts(db: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "entities",
        "entity_identifiers",
        "entity_relations",
        "entity_measurements",
        "concepts",
        "entity_concepts",
        "entity_concept_references",
        "entity_content_guide_dimensions",
        "entity_content_guide_references",
        "entity_restrictions",
        "entity_restriction_references",
        "source_references",
    )
    counts = {table: table_count(db, table) for table in tables}
    counts["catalogued_entities"] = int(
        db.execute("select count(*) from entities where is_catalogued = 1").fetchone()[0]
    )
    return counts


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
