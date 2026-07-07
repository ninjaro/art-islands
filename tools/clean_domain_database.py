#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "art-islands.sqlite"
DEFAULT_TARGET = ROOT / "data" / "art-islands.domain-clean.sqlite"
DEFAULT_INVENTORY = ROOT / "database-cleanup-inventory.md"


TABLE_ACTIONS: dict[str, tuple[str, str]] = {
    "advisory_categories": ("keep", "Normalized content advisory category definitions."),
    "age_rating_systems": ("keep", "Normalized parental/content rating systems."),
    "concept_categories": ("keep", "Domain concept category definitions."),
    "concepts": ("keep", "Domain concepts derived from tags and enrichment."),
    "content_guide_categories": ("trim", "Content-guide categories are domain data; raw JSON and update timestamps are not."),
    "data_patch_applications": ("remove", "Patch application history and batch accounting."),
    "data_sources": ("trim", "Source catalog definitions used by retained source records; unreferenced patch-archive definitions are removed."),
    "entities": ("trim", "Entity identity/display data is kept; review/import/cache columns are removed."),
    "entity_advisories": ("trim", "Human-readable advisories and scores are kept; raw payloads and import links are removed."),
    "entity_age_ratings": ("trim", "Ratings are kept; raw payloads and embedded reference JSON are normalized."),
    "entity_concept_patch_metadata": ("migrate", "Patch metadata is removed after source-reference mappings are extracted."),
    "entity_concepts": ("trim", "Concept assignments are kept; source links remain resolvable and curation provenance flags are removed."),
    "entity_content_guide_dimensions": ("trim", "Content-guide scores are kept; raw patch payloads are normalized away."),
    "entity_dates": ("keep", "Domain dates and source links."),
    "entity_facts": ("remove", "Empty staging/fact table in the current database."),
    "entity_identifiers": ("keep", "External identifiers and their source links."),
    "entity_link_refs": ("keep", "Legacy relationship-to-source mappings."),
    "entity_links": ("keep", "Compact semantic links used by the current app."),
    "entity_measurements": ("keep", "Duration, page counts, dimensions, and source links."),
    "entity_refs": ("keep", "Compact external references used by CLI/export/batches."),
    "entity_relations": ("trim", "Contributor/creator/semantic relationships are kept; manual/import flags are removed."),
    "entity_restrictions": ("trim", "Restriction facts are kept; raw payloads and embedded reference JSON are normalized."),
    "entity_tag_refs": ("keep", "Legacy tag-to-source mappings."),
    "entity_tags": ("keep", "Entity tag weights and polarity."),
    "entity_texts": ("keep", "Labels, aliases, descriptions, and source links."),
    "entity_type_definitions": ("keep", "Entity type definitions."),
    "entity_types": ("keep", "Entity type assignments and source links."),
    "identifier_schemes": ("keep", "External identifier scheme definitions."),
    "measurement_types": ("keep", "Measurement type definitions."),
    "patch_references": ("trim", "Citation catalog is kept; raw JSON and retrieval/update timestamps are removed."),
    "relation_types": ("keep", "Semantic relationship type definitions."),
    "schema_migrations": ("remove", "Migration history."),
    "source_records": ("trim", "Current source identities are kept; file offsets, hashes, timestamps, payload metadata, and unreferenced patch-archive records are removed."),
    "tags": ("keep", "Tag definitions."),
}

REMOVED_COLUMNS: dict[str, dict[str, str]] = {
    "content_guide_categories": {
        "raw_json": "serialized copy of category definition",
        "updated_at": "database update timestamp",
    },
    "entities": {
        "completeness_status": "processing/review status",
        "confidence": "entity-level enrichment confidence, not displayed or required",
        "review_state": "review workflow state",
        "canonical_source_record_id": "import provenance pointer",
        "created_at": "database creation timestamp",
        "updated_at": "database update timestamp",
    },
    "entity_advisories": {
        "is_manual": "curation provenance flag",
        "source_record_id": "patch/import provenance; source citations are normalized into mapping tables",
        "reference_ids_json": "embedded source references migrated to entity_advisory_patch_refs",
        "raw_json": "serialized patch payload",
    },
    "entity_age_ratings": {
        "source_record_id": "patch/import provenance; source citations are normalized into mapping tables",
        "reference_ids_json": "embedded source references migrated to entity_age_rating_patch_refs",
        "raw_json": "serialized patch payload",
    },
    "entity_concept_patch_metadata": {
        "*": "patch/evidence history table removed after reference mappings are extracted",
    },
    "entity_content_guide_dimensions": {
        "source_basis": "mining/editorial rationale rather than a rating value",
        "reference_ids_json": "embedded source references migrated to entity_content_guide_patch_refs",
        "evidence_json": "serialized evidence labels/modes duplicated from normalized tags and raw payloads",
        "context_flags_json": "pipeline context flags; meaningful context is kept in context_json",
        "entity_references_json": "duplicates entity external identifiers",
        "raw_json": "serialized patch payload; unique numeric ratings are migrated to dimension_values_json",
        "source_record_id": "patch/import provenance; source citations are normalized into mapping tables",
        "updated_at": "database update timestamp",
    },
    "entity_concepts": {
        "is_manual": "curation provenance flag",
    },
    "entity_relations": {
        "is_manual": "curation provenance flag",
    },
    "entity_restrictions": {
        "source_record_id": "patch/import provenance; source citations are normalized into mapping tables",
        "reference_ids_json": "embedded source references migrated to entity_restriction_patch_refs",
        "raw_json": "serialized patch payload",
    },
    "patch_references": {
        "retrieved_at": "retrieval timestamp, not source publication date",
        "raw_json": "serialized citation row",
        "source_record_id": "patch/import provenance pointer",
        "updated_at": "database update timestamp",
    },
    "source_records": {
        "local_path": "source file path used during mining/import",
        "retrieved_at": "import/retrieval timestamp",
        "payload_hash": "raw payload recovery/debug hash",
        "revision_id": "import revision metadata",
        "metadata_json": "file offsets and staging metadata",
    },
}

BASE_CONTENT_DIMENSION_KEYS = {
    "entityId",
    "categoryCode",
    "scaleVersion",
    "medium",
    "intensity",
    "centrality",
    "explicitness",
    "realism",
    "recurrence",
    "sensoryImpact",
    "coercion",
    "avoidancePriority",
    "narrativeProximity",
    "languageDependency",
    "guidanceLevel",
    "contentRole",
    "stance",
    "genreContext",
    "confidence",
    "uncertainty",
    "referenceIds",
    "existingLegacyRefIds",
    "entityReferences",
    "evidenceLabels",
    "sourceBasis",
    "op",
    "contextFlags",
    "depictionModes",
    "presentationModes",
    "exposureChannels",
    "tagContext",
}

CONTENT_CONTEXT_KEYS = (
    "contextFlags",
    "depictionModes",
    "presentationModes",
    "exposureChannels",
    "tagContext",
)


SCHEMA = """
pragma journal_mode = delete;
pragma foreign_keys = on;

create table data_sources (
    data_source_id integer primary key,
    code           text not null unique,
    label          text not null,
    source_type    text not null,
    base_url       text
);

create table source_records (
    source_record_id integer primary key,
    data_source_id   integer not null references data_sources(data_source_id),
    external_id      text,
    source_url       text
);
create index source_records_source_idx
on source_records(data_source_id, external_id);

create table entities (
    entity_id          integer primary key,
    label              text not null,
    entity_kind        integer not null default 0,
    release_date       text,
    date_precision     integer not null default 0,
    is_catalogued      integer not null default 0,
    image_ref          text,
    short_description  text,
    entity_family      text,
    check (entity_kind between 0 and 255),
    check (date_precision between 0 and 3),
    check (is_catalogued in (0, 1))
);
create index entities_catalog_date_idx
on entities(is_catalogued, release_date, label);

create table entity_refs (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    ref_kind   integer not null,
    ref_value  text not null,
    primary key (entity_id, ref_kind),
    unique (ref_kind, ref_value),
    check (ref_kind between 0 and 255)
) without rowid;

create table tags (
    tag_id       integer primary key,
    name         text not null unique,
    description  text,
    tag_kind     integer not null default 0,
    namespace    text,
    value        text,
    check (tag_kind between 0 and 255)
);

create table entity_tags (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    tag_id     integer not null references tags(tag_id) on delete cascade,
    weight     integer not null default 50,
    polarity   integer not null default 0,
    primary key (entity_id, tag_id),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
) without rowid;
create index entity_tags_tag_idx
on entity_tags(tag_id, entity_id);

create table entity_links (
    source_entity_id  integer not null references entities(entity_id) on delete cascade,
    target_entity_id  integer not null references entities(entity_id) on delete cascade,
    link_kind         integer not null default 0,
    weight            integer not null default 25,
    polarity          integer not null default 0,
    legacy_tag_id     integer references tags(tag_id) on delete set null,
    primary key (source_entity_id, target_entity_id, link_kind),
    check (link_kind between 0 and 255),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
) without rowid;
create index entity_links_target_idx
on entity_links(target_entity_id, source_entity_id);

create table entity_tag_refs (
    entity_id  integer not null,
    tag_id     integer not null,
    ref_id     integer not null references source_records(source_record_id),
    primary key (entity_id, tag_id, ref_id),
    foreign key (entity_id, tag_id)
        references entity_tags(entity_id, tag_id)
        on delete cascade
) without rowid;

create table entity_link_refs (
    source_entity_id  integer not null,
    target_entity_id  integer not null,
    link_kind         integer not null,
    ref_id            integer not null references source_records(source_record_id),
    primary key (source_entity_id, target_entity_id, link_kind, ref_id),
    foreign key (source_entity_id, target_entity_id, link_kind)
        references entity_links(source_entity_id, target_entity_id, link_kind)
        on delete cascade
) without rowid;

create table identifier_schemes (
    identifier_scheme_id integer primary key,
    code                 text not null unique,
    label                text not null,
    entity_family        text,
    value_pattern        text,
    url_template         text
);

create table entity_identifiers (
    entity_identifier_id  integer primary key,
    entity_id             integer not null references entities(entity_id) on delete cascade,
    identifier_scheme_id  integer not null references identifier_schemes(identifier_scheme_id),
    value                 text not null,
    is_primary            integer not null default 0,
    source_record_id      integer references source_records(source_record_id),
    unique (identifier_scheme_id, value),
    check (is_primary in (0, 1))
);
create index entity_identifiers_entity_idx
on entity_identifiers(entity_id, identifier_scheme_id);

create table entity_type_definitions (
    entity_type_id integer primary key,
    code           text not null unique,
    family         text not null,
    label          text not null,
    description    text
);

create table entity_types (
    entity_id        integer not null references entities(entity_id) on delete cascade,
    entity_type_id   integer not null references entity_type_definitions(entity_type_id),
    is_primary       integer not null default 0,
    confidence       real,
    source_record_id integer references source_records(source_record_id),
    primary key (entity_id, entity_type_id),
    check (is_primary in (0, 1))
) without rowid;
create index entity_types_type_idx
on entity_types(entity_type_id, entity_id);

create table entity_texts (
    entity_text_id   integer primary key,
    entity_id        integer not null references entities(entity_id) on delete cascade,
    text_kind        text not null,
    language         text,
    value            text not null,
    is_primary       integer not null default 0,
    source_record_id integer references source_records(source_record_id),
    check (text_kind in ('label', 'alias', 'description')),
    check (is_primary in (0, 1))
);
create index entity_texts_entity_kind_idx
on entity_texts(entity_id, text_kind, language);

create table relation_types (
    relation_type_id integer primary key,
    code             text not null unique,
    label            text not null,
    category         text not null,
    source_family    text,
    target_family    text,
    inverse_code     text
);

create table entity_relations (
    entity_relation_id integer primary key,
    source_entity_id   integer not null references entities(entity_id) on delete cascade,
    target_entity_id   integer not null references entities(entity_id) on delete cascade,
    relation_type_id   integer not null references relation_types(relation_type_id),
    role_label         text,
    character_label    text,
    ordering           integer,
    weight             integer not null default 50,
    confidence         real,
    polarity           integer not null default 0,
    source_record_id   integer references source_records(source_record_id),
    unique (source_entity_id, target_entity_id, relation_type_id, role_label, character_label),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
);
create index entity_relations_source_idx
on entity_relations(source_entity_id, relation_type_id);
create index entity_relations_target_idx
on entity_relations(target_entity_id, relation_type_id);

create table concept_categories (
    concept_category_id integer primary key,
    code                text not null unique,
    label               text not null
);

create table concepts (
    concept_id          integer primary key,
    label               text not null,
    description         text,
    concept_category_id integer not null references concept_categories(concept_category_id),
    canonical_entity_id integer references entities(entity_id),
    namespace           text,
    value               text,
    legacy_tag_id       integer unique references tags(tag_id) on delete set null,
    classification_rule text,
    confidence          real,
    review_recommended  integer not null default 0,
    unique (concept_category_id, label),
    check (review_recommended in (0, 1))
);
create index concepts_category_idx
on concepts(concept_category_id, label);

create table entity_concepts (
    entity_id        integer not null references entities(entity_id) on delete cascade,
    concept_id       integer not null references concepts(concept_id) on delete cascade,
    weight           integer not null default 50,
    polarity         integer not null default 0,
    confidence       real,
    source_record_id integer references source_records(source_record_id),
    primary key (entity_id, concept_id),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
) without rowid;
create index entity_concepts_concept_idx
on entity_concepts(concept_id, entity_id);

create table entity_concept_patch_refs (
    entity_id    integer not null,
    concept_id   integer not null,
    reference_id text not null references patch_references(reference_id),
    primary key (entity_id, concept_id, reference_id),
    foreign key (entity_id, concept_id)
        references entity_concepts(entity_id, concept_id)
        on delete cascade
) without rowid;

create table entity_concept_source_refs (
    entity_id        integer not null,
    concept_id       integer not null,
    source_record_id integer not null references source_records(source_record_id),
    primary key (entity_id, concept_id, source_record_id),
    foreign key (entity_id, concept_id)
        references entity_concepts(entity_id, concept_id)
        on delete cascade
) without rowid;

create table entity_dates (
    entity_date_id      integer primary key,
    entity_id           integer not null references entities(entity_id) on delete cascade,
    date_type           text not null,
    date_value          text not null,
    date_precision      integer not null,
    end_date_value      text,
    end_date_precision  integer,
    country_entity_id   integer references entities(entity_id),
    place_entity_id     integer references entities(entity_id),
    edition_label       text,
    rank                text,
    is_primary          integer not null default 0,
    confidence          real,
    source_record_id    integer references source_records(source_record_id),
    check (date_precision between 0 and 3),
    check (end_date_precision is null or end_date_precision between 0 and 3),
    check (is_primary in (0, 1))
);
create index entity_dates_entity_type_idx
on entity_dates(entity_id, date_type, is_primary);

create table measurement_types (
    measurement_type_id integer primary key,
    code                text not null unique,
    label               text not null,
    default_unit        text
);

create table entity_measurements (
    entity_measurement_id integer primary key,
    entity_id             integer not null references entities(entity_id) on delete cascade,
    measurement_type_id   integer not null references measurement_types(measurement_type_id),
    numeric_value         real,
    text_value            text,
    unit                  text,
    qualifier             text,
    confidence            real,
    source_record_id      integer references source_records(source_record_id)
);
create index entity_measurements_entity_idx
on entity_measurements(entity_id, measurement_type_id);

create table advisory_categories (
    advisory_category_id integer primary key,
    code                 text not null unique,
    label                text not null,
    parent_id            integer references advisory_categories(advisory_category_id)
);

create table entity_advisories (
    entity_advisory_id   integer primary key,
    entity_id            integer not null references entities(entity_id) on delete cascade,
    advisory_category_id integer not null references advisory_categories(advisory_category_id),
    concept_id           integer references concepts(concept_id),
    severity             integer,
    confidence           real,
    description          text,
    intensity            integer,
    uncertainty          integer,
    check (severity is null or severity between 0 and 4)
);

create table entity_advisory_patch_refs (
    entity_advisory_id integer not null references entity_advisories(entity_advisory_id) on delete cascade,
    reference_id       text not null references patch_references(reference_id),
    primary key (entity_advisory_id, reference_id)
) without rowid;

create table age_rating_systems (
    age_rating_system_id integer primary key,
    code                 text not null unique,
    country_code         text,
    label                text not null
);

create table entity_age_ratings (
    entity_age_rating_id integer primary key,
    entity_id            integer not null references entities(entity_id) on delete cascade,
    age_rating_system_id integer not null references age_rating_systems(age_rating_system_id),
    certificate          text not null,
    minimum_age          integer,
    edition_label        text,
    descriptors_json     text,
    rating_date          text,
    unique (entity_id, age_rating_system_id, certificate, edition_label)
);

create table entity_age_rating_patch_refs (
    entity_age_rating_id integer not null references entity_age_ratings(entity_age_rating_id) on delete cascade,
    reference_id         text not null references patch_references(reference_id),
    primary key (entity_age_rating_id, reference_id)
) without rowid;

create table entity_restrictions (
    entity_restriction_id integer primary key,
    entity_id             integer not null references entities(entity_id) on delete cascade,
    country_code          text,
    region_label          text,
    restriction_type      text not null,
    start_date            text,
    end_date              text,
    reason                text,
    edition_label         text,
    status                text
);

create table entity_restriction_patch_refs (
    entity_restriction_id integer not null references entity_restrictions(entity_restriction_id) on delete cascade,
    reference_id          text not null references patch_references(reference_id),
    primary key (entity_restriction_id, reference_id)
) without rowid;

create table patch_references (
    reference_id text primary key,
    kind         text,
    title        text,
    url          text,
    publisher    text,
    locator      text
);

create table content_guide_categories (
    category_code text primary key,
    label         text not null,
    description   text,
    cross_media   integer,
    score_min     integer,
    score_max     integer,
    guide_version text
);

create table entity_content_guide_dimensions (
    entity_id              integer not null references entities(entity_id) on delete cascade,
    category_code          text not null references content_guide_categories(category_code),
    scale_version          text,
    medium                 text,
    intensity              integer,
    centrality             integer,
    explicitness           integer,
    realism                integer,
    recurrence             integer,
    sensory_impact         integer,
    coercion               integer,
    avoidance_priority     integer,
    narrative_proximity    integer,
    language_dependency    integer,
    guidance_level         text,
    content_role           text,
    stance                 text,
    genre_context          text,
    confidence             real,
    uncertainty            integer,
    dimension_values_json  text,
    context_json           text,
    primary key (entity_id, category_code)
) without rowid;

create table entity_content_guide_patch_refs (
    entity_id     integer not null,
    category_code text not null,
    reference_id  text not null references patch_references(reference_id),
    primary key (entity_id, category_code, reference_id),
    foreign key (entity_id, category_code)
        references entity_content_guide_dimensions(entity_id, category_code)
        on delete cascade
) without rowid;

create table entity_content_guide_source_refs (
    entity_id        integer not null,
    category_code    text not null,
    source_record_id integer not null references source_records(source_record_id),
    primary key (entity_id, category_code, source_record_id),
    foreign key (entity_id, category_code)
        references entity_content_guide_dimensions(entity_id, category_code)
        on delete cascade
) without rowid;
"""


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def as_json_or_none(value: Any) -> str | None:
    if value in (None, {}, []):
        return None
    return json_dump(value)


def row_count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"select count(*) from {table}").fetchone()[0])


def table_columns(db: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(db.execute(f"pragma table_info({table})"))


def table_exists(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table,),
    ).fetchone()
    return row is not None


def column_exists(db: sqlite3.Connection, table: str, column: str) -> bool:
    if not table_exists(db, table):
        return False
    return any(row["name"] == column for row in table_columns(db, table))


def table_pk(columns: list[sqlite3.Row]) -> str:
    pk = [row["name"] for row in sorted(columns, key=lambda r: r["pk"]) if row["pk"]]
    return ", ".join(pk) if pk else ""


def code_reference_count(root: Path, table: str) -> int:
    total = 0
    for base in ("src", "tests", "web"):
        path = root / base
        if not path.exists():
            continue
        for file_path in path.rglob("*"):
            if not file_path.is_file() or file_path.suffix not in {".py", ".ts", ".tsx", ".sql"}:
                continue
            try:
                total += file_path.read_text(encoding="utf-8").count(table)
            except UnicodeDecodeError:
                continue
    return total


def source_schema_inventory(db: sqlite3.Connection, root: Path) -> str:
    sizes = {
        row["name"]: int(row["bytes"] or 0)
        for row in db.execute(
            "select name, sum(pgsize) as bytes from dbstat group by name"
        )
    }
    tables = [
        row["name"]
        for row in db.execute("select name from sqlite_master where type = 'table' order by name")
    ]

    lines = [
        "# Art Islands Domain-Preserving Cleanup Inventory",
        "",
        "This inventory was generated before rebuilding the cleaned database. It classifies every source table and records columns removed from trimmed tables.",
        "",
        "| Table | Rows | Approx bytes | Primary key | Foreign keys | Code refs | Action | Domain-data note |",
        "| --- | ---: | ---: | --- | --- | ---: | --- | --- |",
    ]
    for table in tables:
        columns = table_columns(db, table)
        fks = [
            f"{row['from']}->{row['table']}.{row['to']}"
            for row in db.execute(f"pragma foreign_key_list({table})")
        ]
        action, note = TABLE_ACTIONS.get(table, ("review", "Not classified by the cleanup script."))
        lines.append(
            "| {table} | {rows} | {size} | {pk} | {fks} | {refs} | {action} | {note} |".format(
                table=table,
                rows=row_count(db, table),
                size=sizes.get(table, 0),
                pk=table_pk(columns) or "-",
                fks="<br>".join(fks) if fks else "-",
                refs=code_reference_count(root, table),
                action=action,
                note=note.replace("|", "\\|"),
            )
        )

    lines.extend(
        [
            "",
            "## Value Normalization",
            "",
            "- `entity_concepts.source_record_id`: values pointing to `data_patch_archive` source records are set to null because they identify patch application provenance. Real legacy/local-layer source values are retained, and source citations from patch metadata are preserved in `entity_concept_patch_refs` and `entity_concept_source_refs`.",
            "- `source_records` / `data_sources`: `data_patch_archive` records are removed after those patch-provenance pointers are nulled. Retained fact-source mappings continue to resolve to `source_records` or `patch_references`.",
            "",
            "## Removed Columns",
            "",
        ]
    )
    for table, columns in sorted(REMOVED_COLUMNS.items()):
        lines.append(f"### `{table}`")
        for column, reason in sorted(columns.items()):
            lines.append(f"- `{column}`: {reason}; not required to resolve retained foreign keys.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def copy_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
) -> int:
    cols = tuple(columns)
    col_sql = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    rows = src.execute(f"select {col_sql} from {table}").fetchall()
    dst.executemany(
        f"insert into {table}({col_sql}) values ({placeholders})",
        [tuple(row[col] for col in cols) for row in rows],
    )
    return len(rows)


def copy_sources(src: sqlite3.Connection, dst: sqlite3.Connection) -> dict[str, int]:
    source_rows = src.execute(
        """
        select sr.source_record_id, sr.data_source_id, sr.external_id, sr.source_url
        from source_records sr
        join data_sources ds on ds.data_source_id = sr.data_source_id
        where ds.code <> 'data_patch_archive'
        order by sr.source_record_id
        """
    ).fetchall()
    data_source_ids = sorted({int(row["data_source_id"]) for row in source_rows})
    if data_source_ids:
        source_placeholders = ", ".join("?" for _ in data_source_ids)
        data_sources = src.execute(
            f"""
            select data_source_id, code, label, source_type, base_url
            from data_sources
            where data_source_id in ({source_placeholders})
            order by data_source_id
            """,
            tuple(data_source_ids),
        ).fetchall()
    else:
        data_sources = []
    dst.executemany(
        """
        insert into data_sources(data_source_id, code, label, source_type, base_url)
        values (?, ?, ?, ?, ?)
        """,
        [tuple(row) for row in data_sources],
    )
    dst.executemany(
        """
        insert into source_records(source_record_id, data_source_id, external_id, source_url)
        values (?, ?, ?, ?)
        """,
        [tuple(row) for row in source_rows],
    )
    return {"data_sources": len(data_sources), "source_records": len(source_rows)}


def copy_entity_concepts(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    rows = src.execute(
        """
        select ec.entity_id, ec.concept_id, ec.weight, ec.polarity, ec.confidence,
               case when ds.code = 'data_patch_archive' then null else ec.source_record_id end as source_record_id
        from entity_concepts ec
        left join source_records sr on sr.source_record_id = ec.source_record_id
        left join data_sources ds on ds.data_source_id = sr.data_source_id
        order by ec.entity_id, ec.concept_id
        """
    ).fetchall()
    dst.executemany(
        """
        insert into entity_concepts(entity_id, concept_id, weight, polarity, confidence, source_record_id)
        values (?, ?, ?, ?, ?, ?)
        """,
        [tuple(row) for row in rows],
    )
    return len(rows)


def referenced_patch_ids(src: sqlite3.Connection) -> set[str]:
    refs: set[str] = set()
    sources = (
        ("entity_concept_patch_metadata", "reference_ids_json"),
        ("entity_content_guide_dimensions", "reference_ids_json"),
        ("entity_advisories", "reference_ids_json"),
        ("entity_age_ratings", "reference_ids_json"),
        ("entity_restrictions", "reference_ids_json"),
    )
    for table, column in sources:
        if not column_exists(src, table, column):
            continue
        for (raw,) in src.execute(f"select {column} from {table} where {column} is not null"):
            parsed = parse_json(raw)
            if isinstance(parsed, list):
                refs.update(str(item) for item in parsed if item)
    return refs


def insert_patch_references(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    rows = src.execute(
        """
        select reference_id, kind, title, url, publisher, locator
        from patch_references
        order by reference_id
        """
    ).fetchall()
    dst.executemany(
        """
        insert into patch_references(reference_id, kind, title, url, publisher, locator)
        values (?, ?, ?, ?, ?, ?)
        """,
        [tuple(row) for row in rows],
    )
    existing = {row["reference_id"] for row in rows}
    missing = sorted(referenced_patch_ids(src) - existing)
    dst.executemany(
        """
        insert into patch_references(reference_id, kind, title, url, publisher, locator)
        values (?, 'unresolved_reference', ?, null, null, null)
        """,
        [(ref, ref) for ref in missing],
    )
    return len(rows) + len(missing)


def content_dimension_payload(row: sqlite3.Row) -> tuple[str | None, str | None, list[str], list[int]]:
    raw = parse_json(row["raw_json"])
    if not isinstance(raw, dict):
        return None, None, [], []
    extra_dimensions = {
        key: value
        for key, value in raw.items()
        if key not in BASE_CONTENT_DIMENSION_KEYS
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    }
    context = {
        key: raw[key]
        for key in CONTENT_CONTEXT_KEYS
        if key in raw and raw[key] not in (None, [], {})
    }
    patch_refs = [str(item) for item in raw.get("referenceIds") or [] if item]
    source_refs = [
        int(item)
        for item in raw.get("existingLegacyRefIds") or []
        if isinstance(item, int) and not isinstance(item, bool)
    ]
    return as_json_or_none(extra_dimensions), as_json_or_none(context), patch_refs, source_refs


def json_refs(raw: str | None) -> list[str]:
    parsed = parse_json(raw)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item]


def int_json_refs(raw: str | None) -> list[int]:
    parsed = parse_json(raw)
    if not isinstance(parsed, list):
        return []
    return [int(item) for item in parsed if isinstance(item, int) and not isinstance(item, bool)]


def build_clean_database(source: Path, target: Path, inventory: Path) -> dict[str, int]:
    if target.exists():
        target.unlink()

    src = sqlite3.connect(source)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(target)
    dst.row_factory = sqlite3.Row
    dst.execute("pragma foreign_keys = on")

    stats: dict[str, int] = {}
    try:
        inventory.write_text(source_schema_inventory(src, ROOT), encoding="utf-8")
        dst.executescript(SCHEMA)
        stats.update(copy_sources(src, dst))

        for table, columns in (
            (
                "entities",
                (
                    "entity_id",
                    "label",
                    "entity_kind",
                    "release_date",
                    "date_precision",
                    "is_catalogued",
                    "image_ref",
                    "short_description",
                    "entity_family",
                ),
            ),
            ("entity_refs", ("entity_id", "ref_kind", "ref_value")),
            ("tags", ("tag_id", "name", "description", "tag_kind", "namespace", "value")),
            ("entity_tags", ("entity_id", "tag_id", "weight", "polarity")),
            ("entity_links", ("source_entity_id", "target_entity_id", "link_kind", "weight", "polarity", "legacy_tag_id")),
            ("entity_tag_refs", ("entity_id", "tag_id", "ref_id")),
            ("entity_link_refs", ("source_entity_id", "target_entity_id", "link_kind", "ref_id")),
            ("identifier_schemes", ("identifier_scheme_id", "code", "label", "entity_family", "value_pattern", "url_template")),
            ("entity_identifiers", ("entity_identifier_id", "entity_id", "identifier_scheme_id", "value", "is_primary", "source_record_id")),
            ("entity_type_definitions", ("entity_type_id", "code", "family", "label", "description")),
            ("entity_types", ("entity_id", "entity_type_id", "is_primary", "confidence", "source_record_id")),
            ("entity_texts", ("entity_text_id", "entity_id", "text_kind", "language", "value", "is_primary", "source_record_id")),
            ("relation_types", ("relation_type_id", "code", "label", "category", "source_family", "target_family", "inverse_code")),
            (
                "entity_relations",
                (
                    "entity_relation_id",
                    "source_entity_id",
                    "target_entity_id",
                    "relation_type_id",
                    "role_label",
                    "character_label",
                    "ordering",
                    "weight",
                    "confidence",
                    "polarity",
                    "source_record_id",
                ),
            ),
            ("concept_categories", ("concept_category_id", "code", "label")),
            (
                "concepts",
                (
                    "concept_id",
                    "label",
                    "description",
                    "concept_category_id",
                    "canonical_entity_id",
                    "namespace",
                    "value",
                    "legacy_tag_id",
                    "classification_rule",
                    "confidence",
                    "review_recommended",
                ),
            ),
            (
                "entity_dates",
                (
                    "entity_date_id",
                    "entity_id",
                    "date_type",
                    "date_value",
                    "date_precision",
                    "end_date_value",
                    "end_date_precision",
                    "country_entity_id",
                    "place_entity_id",
                    "edition_label",
                    "rank",
                    "is_primary",
                    "confidence",
                    "source_record_id",
                ),
            ),
            ("measurement_types", ("measurement_type_id", "code", "label", "default_unit")),
            (
                "entity_measurements",
                (
                    "entity_measurement_id",
                    "entity_id",
                    "measurement_type_id",
                    "numeric_value",
                    "text_value",
                    "unit",
                    "qualifier",
                    "confidence",
                    "source_record_id",
                ),
            ),
            ("advisory_categories", ("advisory_category_id", "code", "label", "parent_id")),
            (
                "entity_advisories",
                (
                    "entity_advisory_id",
                    "entity_id",
                    "advisory_category_id",
                    "concept_id",
                    "severity",
                    "confidence",
                    "description",
                    "intensity",
                    "uncertainty",
                ),
            ),
            ("age_rating_systems", ("age_rating_system_id", "code", "country_code", "label")),
            (
                "entity_age_ratings",
                (
                    "entity_age_rating_id",
                    "entity_id",
                    "age_rating_system_id",
                    "certificate",
                    "minimum_age",
                    "edition_label",
                    "descriptors_json",
                    "rating_date",
                ),
            ),
            (
                "entity_restrictions",
                (
                    "entity_restriction_id",
                    "entity_id",
                    "country_code",
                    "region_label",
                    "restriction_type",
                    "start_date",
                    "end_date",
                    "reason",
                    "edition_label",
                    "status",
                ),
            ),
            ("content_guide_categories", ("category_code", "label", "description", "cross_media", "score_min", "score_max", "guide_version")),
        ):
            stats[table] = copy_table(src, dst, table, columns)

        stats["entity_concepts"] = copy_entity_concepts(src, dst)

        stats["patch_references"] = insert_patch_references(src, dst)

        if table_exists(src, "entity_concept_patch_metadata"):
            concept_patch_refs = []
            concept_source_refs = []
            for row in src.execute(
                """
                select entity_id, concept_id, reference_ids_json, existing_legacy_ref_ids_json
                from entity_concept_patch_metadata
                """
            ):
                for ref in json_refs(row["reference_ids_json"]):
                    concept_patch_refs.append((row["entity_id"], row["concept_id"], ref))
                for ref in int_json_refs(row["existing_legacy_ref_ids_json"]):
                    concept_source_refs.append((row["entity_id"], row["concept_id"], ref))
            dst.executemany(
                "insert or ignore into entity_concept_patch_refs(entity_id, concept_id, reference_id) values (?, ?, ?)",
                concept_patch_refs,
            )
            dst.executemany(
                "insert or ignore into entity_concept_source_refs(entity_id, concept_id, source_record_id) values (?, ?, ?)",
                concept_source_refs,
            )
            stats["entity_concept_patch_refs"] = len(concept_patch_refs)
            stats["entity_concept_source_refs"] = len(concept_source_refs)
        else:
            stats["entity_concept_patch_refs"] = copy_table(
                src,
                dst,
                "entity_concept_patch_refs",
                ("entity_id", "concept_id", "reference_id"),
            )
            stats["entity_concept_source_refs"] = copy_table(
                src,
                dst,
                "entity_concept_source_refs",
                ("entity_id", "concept_id", "source_record_id"),
            )

        if column_exists(src, "entity_content_guide_dimensions", "raw_json"):
            guide_rows = []
            guide_patch_refs = []
            guide_source_refs = []
            for row in src.execute("select * from entity_content_guide_dimensions"):
                dimensions, context, patch_refs, source_refs = content_dimension_payload(row)
                guide_rows.append(
                    (
                        row["entity_id"],
                        row["category_code"],
                        row["scale_version"],
                        row["medium"],
                        row["intensity"],
                        row["centrality"],
                        row["explicitness"],
                        row["realism"],
                        row["recurrence"],
                        row["sensory_impact"],
                        row["coercion"],
                        row["avoidance_priority"],
                        row["narrative_proximity"],
                        row["language_dependency"],
                        row["guidance_level"],
                        row["content_role"],
                        row["stance"],
                        row["genre_context"],
                        row["confidence"],
                        row["uncertainty"],
                        dimensions,
                        context,
                    )
                )
                for ref in patch_refs:
                    guide_patch_refs.append((row["entity_id"], row["category_code"], ref))
                for ref in source_refs:
                    guide_source_refs.append((row["entity_id"], row["category_code"], ref))
            dst.executemany(
                """
                insert into entity_content_guide_dimensions(
                    entity_id, category_code, scale_version, medium, intensity,
                    centrality, explicitness, realism, recurrence, sensory_impact,
                    coercion, avoidance_priority, narrative_proximity, language_dependency,
                    guidance_level, content_role, stance, genre_context, confidence,
                    uncertainty, dimension_values_json, context_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                guide_rows,
            )
            dst.executemany(
                "insert or ignore into entity_content_guide_patch_refs(entity_id, category_code, reference_id) values (?, ?, ?)",
                guide_patch_refs,
            )
            dst.executemany(
                "insert or ignore into entity_content_guide_source_refs(entity_id, category_code, source_record_id) values (?, ?, ?)",
                guide_source_refs,
            )
            stats["entity_content_guide_dimensions"] = len(guide_rows)
            stats["entity_content_guide_patch_refs"] = len(guide_patch_refs)
            stats["entity_content_guide_source_refs"] = len(guide_source_refs)
        else:
            stats["entity_content_guide_dimensions"] = copy_table(
                src,
                dst,
                "entity_content_guide_dimensions",
                (
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
                    "dimension_values_json",
                    "context_json",
                ),
            )
            stats["entity_content_guide_patch_refs"] = copy_table(
                src,
                dst,
                "entity_content_guide_patch_refs",
                ("entity_id", "category_code", "reference_id"),
            )
            stats["entity_content_guide_source_refs"] = copy_table(
                src,
                dst,
                "entity_content_guide_source_refs",
                ("entity_id", "category_code", "source_record_id"),
            )

        for table, id_column, target in (
            ("entity_advisories", "entity_advisory_id", "entity_advisory_patch_refs"),
            ("entity_age_ratings", "entity_age_rating_id", "entity_age_rating_patch_refs"),
            ("entity_restrictions", "entity_restriction_id", "entity_restriction_patch_refs"),
        ):
            if column_exists(src, table, "reference_ids_json"):
                refs = []
                for row in src.execute(f"select {id_column}, reference_ids_json from {table} where reference_ids_json is not null"):
                    refs.extend((row[id_column], ref) for ref in json_refs(row["reference_ids_json"]))
                dst.executemany(
                    f"insert or ignore into {target}({id_column}, reference_id) values (?, ?)",
                    refs,
                )
                stats[target] = len(refs)
            else:
                stats[target] = copy_table(src, dst, target, (id_column, "reference_id"))

        dst.commit()
        validate(dst)
        dst.execute("vacuum")
        dst.commit()
    finally:
        src.close()
        dst.close()

    return stats


def validate(db: sqlite3.Connection) -> None:
    integrity = db.execute("pragma integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"integrity_check failed: {integrity}")
    fk = db.execute("pragma foreign_key_check").fetchall()
    if fk:
        raise RuntimeError(f"foreign_key_check failed: {fk[:10]}")

    checks = {
        "entity_tag_refs": """
            select count(*) from entity_tag_refs
            where ref_id not in (select source_record_id from source_records)
        """,
        "entity_link_refs": """
            select count(*) from entity_link_refs
            where ref_id not in (select source_record_id from source_records)
        """,
        "entity_concept_patch_refs": """
            select count(*) from entity_concept_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entity_concept_source_refs": """
            select count(*) from entity_concept_source_refs
            where source_record_id not in (select source_record_id from source_records)
        """,
        "entity_content_guide_patch_refs": """
            select count(*) from entity_content_guide_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entity_content_guide_source_refs": """
            select count(*) from entity_content_guide_source_refs
            where source_record_id not in (select source_record_id from source_records)
        """,
        "entity_advisory_patch_refs": """
            select count(*) from entity_advisory_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entity_age_rating_patch_refs": """
            select count(*) from entity_age_rating_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
        "entity_restriction_patch_refs": """
            select count(*) from entity_restriction_patch_refs
            where reference_id not in (select reference_id from patch_references)
        """,
    }
    for name, sql in checks.items():
        count = int(db.execute(sql).fetchone()[0])
        if count:
            raise RuntimeError(f"logical source orphan check failed for {name}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a domain-preserving compact Art Islands SQLite database.")
    parser.add_argument("--source", type=Path, default=DEFAULT_DB)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = build_clean_database(args.source, args.target, args.inventory)
    print(json_dump({"target": str(args.target), "inventory": str(args.inventory), "stats": stats}))


if __name__ == "__main__":
    main()
