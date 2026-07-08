#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from art_islands.schema import DOMAIN_SCHEMA


DEFAULT_DB = ROOT / "data" / "art-islands.sqlite"
DEFAULT_TARGET = ROOT / "data" / "art-islands.simplified.sqlite"

REPORTS = {
    "pre": ROOT / "database-simplify-pre.md",
    "post": ROOT / "database-simplify-post.md",
    "removed": ROOT / "database-simplify-removed.md",
    "weights": ROOT / "database-simplify-placeholder-weights.md",
    "refs": ROOT / "database-simplify-reference-dedup.md",
}

KEEP_TABLES = {
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
    "source_references",
    "entity_concept_references",
    "entity_dates",
    "measurement_types",
    "entity_measurements",
    "content_guide_categories",
    "entity_content_guide_dimensions",
    "entity_content_guide_references",
    "entity_restrictions",
    "entity_restriction_references",
}

REMOVED_TABLE_REASONS = {
    "tags": "Legacy V1 tag definitions superseded by concepts.",
    "entity_tags": "Legacy V1 assignments superseded by entity_concepts.",
    "entity_tag_refs": "Legacy import-source mappings; curated references are retained in entity_concept_references.",
    "entity_links": "Legacy compact links; explicit normalized relations are retained in entity_relations.",
    "entity_link_refs": "Reference layer for removed legacy compact links.",
    "entity_refs": "Legacy compact identifiers superseded by entity_identifiers.",
    "data_sources": "Import-source catalog, not curated citation evidence.",
    "source_records": "Import-source records and local-layer provenance, not curated citation evidence.",
    "entity_concept_source_refs": "Local import provenance; curated references are retained separately.",
    "entity_content_guide_source_refs": "Local import provenance; curated references are retained separately.",
    "advisory_categories": "Merged into content_guide_categories.",
    "entity_advisories": "Merged into entity_content_guide_dimensions.",
    "entity_advisory_patch_refs": "Merged into entity_content_guide_references.",
    "age_rating_systems": "Coarse certificates removed in favor of detailed 100-point content guide.",
    "entity_age_ratings": "Coarse certificates removed in favor of detailed 100-point content guide.",
    "entity_age_rating_patch_refs": "Reference layer for removed coarse certificate rows.",
    "patch_references": "Renamed to source_references and deduplicated by URL plus locator.",
    "entity_concept_patch_refs": "Renamed to entity_concept_references.",
    "entity_content_guide_patch_refs": "Renamed to entity_content_guide_references.",
    "entity_restriction_patch_refs": "Renamed to entity_restriction_references.",
}

REMOVED_COLUMNS = {
    "concepts": {
        "legacy_tag_id": "Legacy V1 bridge identifier.",
        "classification_rule": "Generation/workflow classification rule.",
        "review_recommended": "Review queue flag.",
    },
    "entity_concepts": {"source_record_id": "Import-source provenance; curated references are mapped separately."},
    "entity_dates": {
        "end_date_value": "Empty in the current database.",
        "end_date_precision": "Empty in the current database.",
        "country_entity_id": "Empty in the current database.",
        "place_entity_id": "Empty in the current database.",
        "edition_label": "Empty in the current database.",
        "source_record_id": "Import-source provenance.",
    },
    "entity_identifiers": {"source_record_id": "Import-source provenance."},
    "entity_measurements": {
        "text_value": "Empty in the current database.",
        "qualifier": "Empty in the current database.",
        "source_record_id": "Import-source provenance.",
    },
    "entity_relations": {
        "role_label": "Empty in the current database.",
        "character_label": "Empty in the current database.",
        "ordering": "Empty in the current database.",
        "polarity": "Constant zero in the current database.",
        "source_record_id": "Import-source provenance.",
    },
    "entity_texts": {"source_record_id": "Import-source provenance."},
    "entity_types": {"source_record_id": "Import-source provenance."},
}


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("pragma foreign_keys = on")
    return db


def table_names(db: sqlite3.Connection) -> list[str]:
    return [
        row["name"]
        for row in db.execute(
            "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by name"
        )
    ]


def table_count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"select count(*) from {table}").fetchone()[0])


def dbstat_sizes(db: sqlite3.Connection) -> dict[str, int]:
    try:
        return {
            row["name"]: int(row["bytes"])
            for row in db.execute("select name, sum(pgsize) as bytes from dbstat group by name")
        }
    except sqlite3.DatabaseError:
        return {}


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def column_stats(db: sqlite3.Connection, table: str, column: str) -> tuple[int, int, int]:
    row = db.execute(
        f"""
        select count(*) as rows,
               sum(case when {quote(column)} is null then 1 else 0 end) as nulls,
               count(distinct {quote(column)}) as distincts
        from {quote(table)}
        """
    ).fetchone()
    return int(row["rows"]), int(row["nulls"] or 0), int(row["distincts"] or 0)


def inventory(db: sqlite3.Connection) -> dict[str, Any]:
    sizes = dbstat_sizes(db)
    output: dict[str, Any] = {}
    for table in table_names(db):
        columns = [dict(row) for row in db.execute(f"pragma table_info({quote(table)})")]
        output[table] = {
            "rows": table_count(db, table),
            "bytes": sizes.get(table, 0),
            "columns": [row["name"] for row in columns],
            "primaryKey": [row["name"] for row in columns if row["pk"]],
            "foreignKeys": [dict(row) for row in db.execute(f"pragma foreign_key_list({quote(table)})")],
            "indexes": [dict(row) for row in db.execute(f"pragma index_list({quote(table)})")],
        }
    return output


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_pre_report(db: sqlite3.Connection, db_path: Path) -> None:
    inv = inventory(db)
    lines = [
        "# Art Islands Domain Simplification Pre-Migration Audit",
        "",
        f"- Database: `{db_path}`",
        f"- File size: {db_path.stat().st_size:,} bytes",
        f"- Integrity: {db.execute('pragma integrity_check').fetchone()[0]}",
        f"- Foreign-key errors: {len(db.execute('pragma foreign_key_check').fetchall())}",
        "",
        "## Table Inventory",
        "",
        "| Table | Rows | Approx bytes | Action |",
        "| --- | ---: | ---: | --- |",
    ]
    for table, info in inv.items():
        if table in KEEP_TABLES:
            action = "keep"
        elif table in REMOVED_TABLE_REASONS:
            action = "remove/merge"
        else:
            action = "remove"
        lines.append(f"| `{table}` | {info['rows']:,} | {info['bytes']:,} | {action} |")
    lines.extend(["", "## Columns Marked For Removal", ""])
    for table, columns in sorted(REMOVED_COLUMNS.items()):
        if table not in inv:
            continue
        for column, reason in sorted(columns.items()):
            if column not in inv[table]["columns"]:
                continue
            rows, nulls, distincts = column_stats(db, table, column)
            lines.append(
                f"- `{table}.{column}`: rows={rows:,}; nulls={nulls:,}; distinct={distincts:,}. {reason}"
            )
    write_lines(REPORTS["pre"], lines)


def normalize_url(url: str | None) -> str | None:
    if url is None:
        return None
    value = url.strip().lower()
    return value or None


def build_reference_mapping(source: sqlite3.Connection) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = [
        dict(row)
        for row in source.execute(
            "select reference_id, kind, title, url, publisher, locator from patch_references order by reference_id"
        )
    ]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for row in rows:
        url = normalize_url(row["url"])
        if url is None:
            passthrough.append(row)
        else:
            groups[(url, row["locator"] or "")].append(row)

    mapping: dict[str, str] = {}
    kept: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    for row in passthrough:
        mapping[row["reference_id"]] = row["reference_id"]
        kept.append(row)
    for key, group in sorted(groups.items()):
        canonical = sorted(group, key=lambda row: (len(row["reference_id"]), row["reference_id"]))[0]
        kept.append(canonical)
        for row in group:
            mapping[row["reference_id"]] = canonical["reference_id"]
            if row["reference_id"] != canonical["reference_id"]:
                merged.append(
                    {
                        "from": row["reference_id"],
                        "to": canonical["reference_id"],
                        "url": key[0],
                        "locator": key[1],
                    }
                )
    kept.sort(key=lambda row: row["reference_id"])
    return mapping, kept, merged


def useful_advisory_description(description: str | None) -> str | None:
    if not description:
        return None
    text = description.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("source-derived") or lowered.startswith("reference-derived"):
        return None
    return text


def compact_context_json(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(value, dict):
        return raw
    value.pop("tagContext", None)
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def copy_rows(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> int:
    col_sql = ", ".join(columns)
    rows = source.execute(f"select {col_sql} from {table} order by 1").fetchall()
    placeholders = ", ".join("?" for _ in columns)
    target.executemany(
        f"insert into {table}({col_sql}) values ({placeholders})",
        ([row[column] for column in columns] for row in rows),
    )
    return len(rows)


def copy_domain(source: sqlite3.Connection, target: sqlite3.Connection, ref_mapping: dict[str, str]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for table, columns in (
        ("entities", ("entity_id", "label", "entity_kind", "release_date", "date_precision", "is_catalogued", "image_ref", "short_description", "entity_family")),
        ("identifier_schemes", ("identifier_scheme_id", "code", "label", "entity_family", "value_pattern", "url_template")),
        ("entity_type_definitions", ("entity_type_id", "code", "family", "label", "description")),
        ("relation_types", ("relation_type_id", "code", "label", "category", "source_family", "target_family", "inverse_code")),
        ("concept_categories", ("concept_category_id", "code", "label")),
        ("measurement_types", ("measurement_type_id", "code", "label", "default_unit")),
        ("entity_restrictions", ("entity_restriction_id", "entity_id", "country_code", "region_label", "restriction_type", "start_date", "end_date", "reason", "edition_label", "status")),
    ):
        stats[table] = copy_rows(source, target, table, columns)

    stats["entity_identifiers"] = copy_rows(
        source,
        target,
        "entity_identifiers",
        ("entity_identifier_id", "entity_id", "identifier_scheme_id", "value", "is_primary"),
    )
    stats["entity_types"] = copy_rows(
        source, target, "entity_types", ("entity_id", "entity_type_id", "is_primary", "confidence")
    )
    stats["entity_texts"] = copy_rows(
        source, target, "entity_texts", ("entity_text_id", "entity_id", "text_kind", "language", "value", "is_primary")
    )
    stats["entity_dates"] = copy_rows(
        source,
        target,
        "entity_dates",
        ("entity_date_id", "entity_id", "date_type", "date_value", "date_precision", "rank", "is_primary", "confidence"),
    )
    stats["entity_measurements"] = copy_rows(
        source,
        target,
        "entity_measurements",
        ("entity_measurement_id", "entity_id", "measurement_type_id", "numeric_value", "unit", "confidence"),
    )

    relation_rows = source.execute(
        """
        select entity_relation_id, source_entity_id, target_entity_id, relation_type_id, weight, confidence
        from entity_relations
        order by entity_relation_id
        """
    ).fetchall()
    target.executemany(
        """
        insert into entity_relations(
            entity_relation_id, source_entity_id, target_entity_id, relation_type_id, weight, confidence
        ) values (?, ?, ?, ?, ?, ?)
        """,
        relation_rows,
    )
    stats["entity_relations"] = len(relation_rows)

    concept_rows = source.execute(
        """
        select concept_id, label, description, concept_category_id, canonical_entity_id,
               namespace, value, confidence
        from concepts
        order by concept_id
        """
    ).fetchall()
    target.executemany(
        """
        insert into concepts(
            concept_id, label, description, concept_category_id, canonical_entity_id,
            namespace, value, confidence
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        concept_rows,
    )
    stats["concepts"] = len(concept_rows)

    placeholder_counter: Counter[str] = Counter()
    unchanged_50 = 0
    concept_assignments = []
    for row in source.execute(
        """
        select ec.entity_id, ec.concept_id, ec.weight, ec.polarity, ec.confidence, ds.code as source_code
        from entity_concepts ec
        left join source_records sr on sr.source_record_id = ec.source_record_id
        left join data_sources ds on ds.data_source_id = sr.data_source_id
        order by ec.entity_id, ec.concept_id
        """
    ):
        weight = row["weight"]
        if row["source_code"] in {"legacy_database", "local_layer"}:
            placeholder_counter[f"{row['source_code']}:{weight}"] += 1
            weight = None
        elif row["weight"] == 50:
            unchanged_50 += 1
        concept_assignments.append((row["entity_id"], row["concept_id"], weight, row["polarity"], row["confidence"]))
    target.executemany(
        "insert into entity_concepts(entity_id, concept_id, weight, polarity, confidence) values (?, ?, ?, ?, ?)",
        concept_assignments,
    )
    stats["entity_concepts"] = len(concept_assignments)
    stats["placeholder_weights"] = dict(sorted(placeholder_counter.items()))
    stats["unchanged_weight_50"] = unchanged_50

    for reference in sorted(set(ref_mapping.values())):
        pass
    stats["entity_concept_references"] = copy_mapped_refs(
        source,
        target,
        ref_mapping,
        """
        select entity_id, concept_id, reference_id
        from entity_concept_patch_refs
        order by entity_id, concept_id, reference_id
        """,
        "entity_concept_references",
        ("entity_id", "concept_id", "reference_id"),
    )

    copy_content_categories(source, target)
    stats["content_guide_categories"] = table_count(target, "content_guide_categories")
    stats.update(copy_content_guide(source, target, ref_mapping))
    stats["entity_restriction_references"] = copy_mapped_refs(
        source,
        target,
        ref_mapping,
        """
        select entity_restriction_id, reference_id
        from entity_restriction_patch_refs
        order by entity_restriction_id, reference_id
        """,
        "entity_restriction_references",
        ("entity_restriction_id", "reference_id"),
    )
    return stats


def copy_mapped_refs(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    ref_mapping: dict[str, str],
    query: str,
    table: str,
    columns: tuple[str, ...],
) -> int:
    rows = []
    seen = set()
    for row in source.execute(query):
        values = list(row)
        values[-1] = ref_mapping[values[-1]]
        key = tuple(values)
        if key in seen:
            continue
        seen.add(key)
        rows.append(tuple(values))
    placeholders = ", ".join("?" for _ in columns)
    target.executemany(
        f"insert or ignore into {table}({', '.join(columns)}) values ({placeholders})",
        rows,
    )
    return len(rows)


def copy_content_categories(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    target.executemany(
        """
        insert into content_guide_categories(
            category_code, label, description, cross_media, score_min, score_max, guide_version
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        source.execute(
            """
            select category_code, label, description, cross_media, score_min, score_max, guide_version
            from content_guide_categories
            order by category_code
            """
        ).fetchall(),
    )
    for row in source.execute(
        """
        select ac.code, ac.label
        from advisory_categories ac
        left join content_guide_categories c on c.category_code = ac.code
        where c.category_code is null
        order by ac.code
        """
    ):
        target.execute(
            """
            insert into content_guide_categories(
                category_code, label, description, cross_media, score_min, score_max, guide_version
            ) values (?, ?, null, 1, 0, 100, null)
            """,
            (row["code"], row["label"]),
        )


CONTENT_COLUMNS = (
    "entity_id",
    "category_code",
    "scale_version",
    "medium",
    "intensity",
    "centrality",
    "explicitness",
    "realism",
    "recurrence",
    "sensory_impact",
    "coercion",
    "avoidance_priority",
    "narrative_proximity",
    "language_dependency",
    "guidance_level",
    "content_role",
    "stance",
    "genre_context",
    "confidence",
    "uncertainty",
    "description",
    "dimension_values_json",
    "context_json",
)


def copy_content_guide(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    ref_mapping: dict[str, str],
) -> dict[str, int]:
    useful_descriptions: dict[tuple[int, str], list[str]] = defaultdict(list)
    advisory_rows = source.execute(
        """
        select a.entity_advisory_id, a.entity_id, c.code as category_code,
               a.confidence, a.description, a.intensity, a.uncertainty
        from entity_advisories a
        join advisory_categories c on c.advisory_category_id = a.advisory_category_id
        order by a.entity_advisory_id
        """
    ).fetchall()
    for row in advisory_rows:
        description = useful_advisory_description(row["description"])
        if description:
            key = (int(row["entity_id"]), row["category_code"])
            if description not in useful_descriptions[key]:
                useful_descriptions[key].append(description)

    existing_keys = set()
    content_rows = []
    for row in source.execute(
        """
        select entity_id, category_code, scale_version, medium, intensity,
               centrality, explicitness, realism, recurrence, sensory_impact,
               coercion, avoidance_priority, narrative_proximity, language_dependency,
               guidance_level, content_role, stance, genre_context, confidence,
               uncertainty, dimension_values_json, context_json
        from entity_content_guide_dimensions
        order by entity_id, category_code
        """
    ):
        key = (int(row["entity_id"]), row["category_code"])
        existing_keys.add(key)
        description = "\n".join(useful_descriptions.get(key, ())) or None
        content_rows.append(
            tuple(row[column] for column in CONTENT_COLUMNS[:20])
            + (description, row["dimension_values_json"], compact_context_json(row["context_json"]))
        )

    advisory_only = 0
    for row in advisory_rows:
        key = (int(row["entity_id"]), row["category_code"])
        if key in existing_keys:
            continue
        advisory_only += 1
        content_rows.append(
            (
                row["entity_id"],
                row["category_code"],
                None,
                None,
                row["intensity"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                row["confidence"],
                row["uncertainty"],
                "\n".join(useful_descriptions.get(key, ())) or None,
                None,
                None,
            )
        )
        existing_keys.add(key)

    target.executemany(
        f"insert into entity_content_guide_dimensions({', '.join(CONTENT_COLUMNS)}) values ({', '.join('?' for _ in CONTENT_COLUMNS)})",
        content_rows,
    )

    guide_refs = []
    seen_refs = set()
    for row in source.execute(
        """
        select entity_id, category_code, reference_id
        from entity_content_guide_patch_refs
        order by entity_id, category_code, reference_id
        """
    ):
        key = (row["entity_id"], row["category_code"], ref_mapping[row["reference_id"]])
        if key not in seen_refs:
            guide_refs.append(key)
            seen_refs.add(key)
    for row in source.execute(
        """
        select a.entity_id, c.code as category_code, r.reference_id
        from entity_advisory_patch_refs r
        join entity_advisories a on a.entity_advisory_id = r.entity_advisory_id
        join advisory_categories c on c.advisory_category_id = a.advisory_category_id
        order by a.entity_id, c.code, r.reference_id
        """
    ):
        key = (row["entity_id"], row["category_code"], ref_mapping[row["reference_id"]])
        if key not in seen_refs:
            guide_refs.append(key)
            seen_refs.add(key)
    target.executemany(
        """
        insert or ignore into entity_content_guide_references(entity_id, category_code, reference_id)
        values (?, ?, ?)
        """,
        guide_refs,
    )

    return {
        "entity_content_guide_dimensions": len(content_rows),
        "advisory_only_content_rows_migrated": advisory_only,
        "entity_content_guide_references": len(guide_refs),
        "useful_advisory_descriptions": sum(len(values) for values in useful_descriptions.values()),
    }


def write_source_references(target: sqlite3.Connection, references: list[dict[str, Any]]) -> int:
    target.executemany(
        """
        insert into source_references(reference_id, source_type, title, url, publisher, locator)
        values (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                row["reference_id"],
                row["kind"],
                row["title"],
                row["url"],
                row["publisher"],
                row["locator"],
            )
            for row in references
        ),
    )
    return len(references)


def validate(source: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, Any]:
    source_catalog_qids = {
        row["value"]
        for row in source.execute(
            """
            select i.value
            from entities e
            join entity_identifiers i on i.entity_id = e.entity_id
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            where e.is_catalogued = 1 and s.code = 'wikidata'
            """
        )
    }
    target_catalog_qids = {
        row["value"]
        for row in target.execute(
            """
            select i.value
            from entities e
            join entity_identifiers i on i.entity_id = e.entity_id
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            where e.is_catalogued = 1 and s.code = 'wikidata'
            """
        )
    }
    result = {
        "quick_check": target.execute("pragma quick_check").fetchone()[0],
        "foreign_key_check": [tuple(row) for row in target.execute("pragma foreign_key_check")],
        "missing_catalog_qids": sorted(source_catalog_qids - target_catalog_qids),
        "extra_catalog_qids": sorted(target_catalog_qids - source_catalog_qids),
        "concept_reference_orphans": table_count_sql(
            target,
            """
            select count(*) from entity_concept_references
            where reference_id not in (select reference_id from source_references)
            """,
        ),
        "content_reference_orphans": table_count_sql(
            target,
            """
            select count(*) from entity_content_guide_references
            where reference_id not in (select reference_id from source_references)
            """,
        ),
        "restriction_reference_orphans": table_count_sql(
            target,
            """
            select count(*) from entity_restriction_references
            where reference_id not in (select reference_id from source_references)
            """,
        ),
    }
    result["ok"] = (
        result["quick_check"] == "ok"
        and not result["foreign_key_check"]
        and not result["missing_catalog_qids"]
        and result["concept_reference_orphans"] == 0
        and result["content_reference_orphans"] == 0
        and result["restriction_reference_orphans"] == 0
    )
    return result


def table_count_sql(db: sqlite3.Connection, sql: str) -> int:
    return int(db.execute(sql).fetchone()[0])


def write_removed_report(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    old_tables = set(table_names(source))
    new_tables = set(table_names(target))
    lines = [
        "# Removed And Merged Structures",
        "",
        "## Removed Or Merged Tables",
        "",
    ]
    for table in sorted(old_tables - new_tables):
        lines.append(f"- `{table}`: {REMOVED_TABLE_REASONS.get(table, 'Not part of the compact current-state schema.')}")
    lines.extend(["", "## Removed Columns From Retained Tables", ""])
    for table, columns in sorted(REMOVED_COLUMNS.items()):
        if table not in old_tables:
            continue
        for column, reason in sorted(columns.items()):
            source_columns = {row["name"] for row in source.execute(f"pragma table_info({quote(table)})")}
            if column not in source_columns:
                continue
            rows, nulls, distincts = column_stats(source, table, column)
            lines.append(
                f"- `{table}.{column}`: rows={rows:,}; nulls={nulls:,}; distinct={distincts:,}. {reason}"
            )
    lines.extend(
        [
            "",
            "## JSON Field Decisions",
            "",
            "- `entity_content_guide_dimensions.dimension_values_json` is retained temporarily because it contains unique detailed 100-point component values not normalized elsewhere.",
            "- `entity_content_guide_dimensions.context_json` is retained after removing duplicated `tagContext` keys; remaining context keys describe current content presentation modes.",
        ]
    )
    write_lines(REPORTS["removed"], lines)


def write_weight_report(stats: dict[str, Any]) -> None:
    lines = [
        "# Placeholder Concept Weights",
        "",
        "Confirmed placeholder origins converted to `NULL`:",
        "",
    ]
    total = 0
    for key, count in sorted(stats["placeholder_weights"].items()):
        source, weight = key.split(":", 1)
        total += count
        lines.append(f"- `{source}` fixed value `{weight}`: {count:,} assignments")
    lines.extend(
        [
            "",
            f"- Total assignments changed to `NULL`: {total:,}",
            f"- Unchanged assignments with numeric weight `50`: {stats['unchanged_weight_50']:,}",
            "- Ambiguous numeric 50 values without a confirmed placeholder origin were left unchanged.",
            "- `NULL` means attached but uncalibrated; no value was converted to `0`.",
        ]
    )
    write_lines(REPORTS["weights"], lines)


def write_reference_report(source: sqlite3.Connection, target: sqlite3.Connection, merged: list[dict[str, Any]]) -> None:
    lines = [
        "# Curated Reference Deduplication",
        "",
        f"- Before references: {table_count(source, 'patch_references'):,}",
        f"- After references: {table_count(target, 'source_references'):,}",
        f"- Merged duplicate reference IDs: {len(merged):,}",
        "",
        "## Merges",
        "",
    ]
    if merged:
        for row in merged:
            lines.append(
                f"- `{row['from']}` -> `{row['to']}` (url=`{row['url']}`, locator=`{row['locator']}`)"
            )
    else:
        lines.append("- None")
    write_lines(REPORTS["refs"], lines)


def write_post_report(
    source_path: Path,
    target_path: Path,
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    stats: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    lines = [
        "# Art Islands Domain Simplification Post-Migration Audit",
        "",
        f"- Original size: {source_path.stat().st_size:,} bytes",
        f"- Cleaned size: {target_path.stat().st_size:,} bytes",
        f"- Size reduction: {source_path.stat().st_size - target_path.stat().st_size:,} bytes",
        f"- Quick check: {validation['quick_check']}",
        f"- Foreign-key errors: {len(validation['foreign_key_check'])}",
        f"- Catalog QIDs missing: {len(validation['missing_catalog_qids'])}",
        "",
        "## Retained Counts",
        "",
        "| Table | Rows |",
        "| --- | ---: |",
    ]
    for table in sorted(KEEP_TABLES):
        if table in table_names(target):
            lines.append(f"| `{table}` | {table_count(target, table):,} |")
    lines.extend(
        [
            "",
            "## Migration Statistics",
            "",
            f"- Advisory-only content-guide rows migrated: {stats['advisory_only_content_rows_migrated']:,}",
            f"- Useful advisory descriptions migrated: {stats['useful_advisory_descriptions']:,}",
            f"- Concept reference mappings retained: {stats['entity_concept_references']:,}",
            f"- Content-guide reference mappings retained: {stats['entity_content_guide_references']:,}",
            f"- Restriction reference mappings retained: {stats['entity_restriction_references']:,}",
            f"- Concept assignments with `NULL` weight after cleanup: {table_count_sql(target, 'select count(*) from entity_concepts where weight is null'):,}",
            "",
            "## Validation",
            "",
            f"- `PRAGMA quick_check`: {validation['quick_check']}",
            f"- `PRAGMA foreign_key_check`: {validation['foreign_key_check']}",
            f"- Logical concept-reference orphans: {validation['concept_reference_orphans']}",
            f"- Logical content-guide-reference orphans: {validation['content_reference_orphans']}",
            f"- Logical restriction-reference orphans: {validation['restriction_reference_orphans']}",
        ]
    )
    write_lines(REPORTS["post"], lines)


def rebuild(db_path: Path, target_path: Path, apply: bool) -> None:
    if target_path.exists():
        target_path.unlink()
    for suffix in ("-wal", "-shm"):
        path = Path(str(target_path) + suffix)
        if path.exists():
            path.unlink()

    source = connect(db_path)
    target = connect(target_path)
    try:
        write_pre_report(source, db_path)
        target.executescript(DOMAIN_SCHEMA)
        ref_mapping, references, merged_refs = build_reference_mapping(source)
        write_source_references(target, references)
        stats = copy_domain(source, target, ref_mapping)
        target.commit()
        target.execute("vacuum")
        target.commit()
        validation = validate(source, target)
        write_removed_report(source, target)
        write_weight_report(stats)
        write_reference_report(source, target, merged_refs)
        write_post_report(db_path, target_path, source, target, stats, validation)
        if not validation["ok"]:
            raise SystemExit(f"validation failed: {json.dumps(validation, sort_keys=True)}")
    finally:
        source.close()
        target.close()

    if apply:
        os.replace(target_path, db_path)
        for suffix in ("-wal", "-shm"):
            path = Path(str(target_path) + suffix)
            if path.exists():
                path.unlink()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    p.add_argument("--apply", action="store_true", help="Replace --db with the validated compact database.")
    return p


def main() -> None:
    args = parser().parse_args()
    rebuild(args.db, args.target, args.apply)


if __name__ == "__main__":
    main()
