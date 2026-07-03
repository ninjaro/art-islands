from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ENTITY_KIND_UNKNOWN = 0
ENTITY_KIND_FILM = 1
ENTITY_KIND_MUSIC_RELEASE = 2
ENTITY_KIND_PERSON = 3
ENTITY_KIND_GROUP = 4
ENTITY_KIND_ORGANIZATION = 5
ENTITY_KIND_GAME = 6
ENTITY_KIND_WORK = 7
ENTITY_KIND_GENRE = 8

REF_KIND_WIKIDATA = 1
REF_KIND_IMDB = 2
REF_KIND_TMDB = 3
REF_KIND_MUSICBRAINZ = 4
REF_KIND_DISCOGS = 5

LINK_KIND_ASSOCIATED = 0
LINK_KIND_INFLUENCED_BY = 1
LINK_KIND_INFLUENCED = 2
LINK_KIND_ADAPTED_FROM = 3
LINK_KIND_RELATED = 4

TAG_KIND_PLAIN = 0
TAG_KIND_NAMESPACED = 1
TAG_KIND_LEGACY_RELATION_TEXT = 2

DEFAULT_ART_LAYER_NAMES = (
    "film",
    "television_series",
    "music_album",
    "book",
    "painting",
    "sculpture",
    "photograph",
    "video_game",
    "comics",
    "musical_work",
)

DATE_CLAIM_PIDS = ("P577", "P571", "P580", "P585")
TITLE_CLAIM_PIDS = ("P1476", "P1448", "P1705")

ASSOCIATED_CLAIM_TARGET_KINDS = {
    "P57": ENTITY_KIND_PERSON,
    "P58": ENTITY_KIND_PERSON,
    "P161": ENTITY_KIND_PERSON,
    "P162": ENTITY_KIND_PERSON,
    "P170": ENTITY_KIND_PERSON,
    "P175": ENTITY_KIND_GROUP,
    "P86": ENTITY_KIND_PERSON,
    "P676": ENTITY_KIND_PERSON,
    "P178": ENTITY_KIND_ORGANIZATION,
    "P123": ENTITY_KIND_ORGANIZATION,
    "P264": ENTITY_KIND_ORGANIZATION,
    "P272": ENTITY_KIND_ORGANIZATION,
    "P750": ENTITY_KIND_ORGANIZATION,
}

CLAIM_LINK_KINDS = {
    LINK_KIND_ASSOCIATED: tuple(ASSOCIATED_CLAIM_TARGET_KINDS),
    LINK_KIND_INFLUENCED_BY: ("P737", "P941"),
    LINK_KIND_ADAPTED_FROM: ("P144",),
}

REF_KIND_LABELS = {
    REF_KIND_WIKIDATA: "wikidata",
    REF_KIND_IMDB: "imdb",
    REF_KIND_TMDB: "tmdb",
    REF_KIND_MUSICBRAINZ: "musicbrainz",
    REF_KIND_DISCOGS: "discogs",
}

DEFAULT_SETTINGS = {
    "recommendation": {
        "likeWeight": 1.0,
        "dislikeWeight": 1.5,
        "limit": 100,
    }
}

QID_RE = re.compile(r"^Q[1-9][0-9]*$")
WIKIDATA_TIME_RE = re.compile(
    r"^(?P<sign>[+-])(?P<year>\d+)-(?P<month>\d{2})-(?P<day>\d{2})T"
)


ART_SCHEMA = """
pragma journal_mode = wal;
pragma foreign_keys = on;

create table if not exists entities (
    entity_id       integer primary key,
    label           text not null,
    entity_kind     integer not null default 0,
    release_date    text,
    date_precision  integer not null default 0,
    is_catalogued   integer not null default 0,
    image_ref       text,

    check (entity_kind between 0 and 255),
    check (date_precision between 0 and 3),
    check (is_catalogued in (0, 1))
);

create table if not exists entity_refs (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    ref_kind   integer not null,
    ref_value  text not null,

    primary key (entity_id, ref_kind),
    unique (ref_kind, ref_value),
    check (ref_kind between 0 and 255)
);

create table if not exists tags (
    tag_id       integer primary key,
    name         text not null unique,
    description  text,
    tag_kind     integer not null default 0,
    namespace    text,
    value        text,

    check (tag_kind between 0 and 255)
);

create table if not exists entity_tags (
    entity_id  integer not null references entities(entity_id) on delete cascade,
    tag_id     integer not null references tags(tag_id) on delete cascade,
    weight     integer not null default 50,
    polarity   integer not null default 0,

    primary key (entity_id, tag_id),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
);

create table if not exists entity_links (
    source_entity_id  integer not null references entities(entity_id) on delete cascade,
    target_entity_id  integer not null references entities(entity_id) on delete cascade,
    link_kind         integer not null default 0,
    weight            integer not null default 25,
    polarity          integer not null default 0,
    legacy_tag_id     integer references tags(tag_id) on delete set null,

    primary key (
        source_entity_id,
        target_entity_id,
        link_kind
    ),
    check (link_kind between 0 and 255),
    check (weight between 0 and 100),
    check (polarity between -1 and 1)
);

create table if not exists entity_tag_refs (
    entity_id  integer not null,
    tag_id     integer not null,
    ref_id     integer not null,

    primary key (entity_id, tag_id, ref_id),
    foreign key (entity_id, tag_id)
        references entity_tags(entity_id, tag_id)
        on delete cascade
);

create table if not exists entity_link_refs (
    source_entity_id  integer not null,
    target_entity_id  integer not null,
    link_kind         integer not null,
    ref_id            integer not null,

    primary key (
        source_entity_id,
        target_entity_id,
        link_kind,
        ref_id
    ),
    foreign key (source_entity_id, target_entity_id, link_kind)
        references entity_links(source_entity_id, target_entity_id, link_kind)
        on delete cascade
);

create index if not exists entities_catalog_date_idx
on entities(is_catalogued, release_date, label);

create index if not exists entity_tags_tag_idx
on entity_tags(tag_id, entity_id);

create index if not exists entity_links_target_idx
on entity_links(target_entity_id, source_entity_id);
"""


@dataclass(frozen=True)
class SourceTag:
    tag_id: int
    name: str
    description: str | None


@dataclass(frozen=True)
class SourcePair:
    pair_id: int
    qid: str
    tag_id: int


@dataclass(frozen=True)
class SourceData:
    tags: dict[int, SourceTag]
    pairs: list[SourcePair]
    pair_refs: dict[int, tuple[int, ...]]


@dataclass(frozen=True)
class ParsedTag:
    tag_kind: int
    namespace: str | None = None
    value: str | None = None
    relation_prefix: str | None = None
    relation_object: str | None = None
    target_qid: str | None = None
    link_kind: int | None = None
    target_kind: int = ENTITY_KIND_UNKNOWN


@dataclass(frozen=True)
class LinkSeed:
    target_qid: str
    link_kind: int
    target_kind: int = ENTITY_KIND_UNKNOWN


@dataclass(frozen=True)
class EntityMetadata:
    label: str = ""
    entity_kind: int = ENTITY_KIND_UNKNOWN
    release_date: str | None = None
    date_precision: int = 0
    image_ref: str | None = None
    refs: tuple[tuple[int, str], ...] = ()
    links: tuple[LinkSeed, ...] = ()


@dataclass(frozen=True)
class MigrationStats:
    entities: int
    catalogued_entities: int
    secondary_entities: int
    tags: int
    entity_tags: int
    entity_links: int
    entity_tag_refs: int
    entity_link_refs: int


def connect_art(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(ART_SCHEMA)
    return db


def remove_sqlite_database(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()


def default_art_layers(root: Path) -> list[Path]:
    return [root / "layers" / f"{name}.jsonl" for name in DEFAULT_ART_LAYER_NAMES]


def qid_sort_key(qid: str) -> tuple[int, str]:
    if QID_RE.fullmatch(qid):
        return (int(qid[1:]), qid)
    return (10**18, qid)


def duckdb_rows(path: Path, sql: str) -> list[dict[str, Any]]:
    try:
        import duckdb  # type: ignore
    except Exception:
        duckdb = None

    if duckdb is not None:
        connection = duckdb.connect(str(path), read_only=True)
        try:
            result = connection.execute(sql)
            columns = [item[0] for item in result.description]
            return [
                {column: value for column, value in zip(columns, row)}
                for row in result.fetchall()
            ]
        finally:
            connection.close()

    executable = shutil.which("duckdb")
    if not executable:
        raise RuntimeError(
            "DuckDB support requires either the duckdb Python package "
            "or a duckdb executable on PATH"
        )

    result = subprocess.run(
        [executable, "-readonly", "-json", str(path), "-c", sql],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "duckdb query failed")
    output = result.stdout.strip()
    if not output:
        return []
    return json.loads(output)


def load_source_data(source_db: Path) -> SourceData:
    tag_rows = duckdb_rows(
        source_db,
        """
        select tag_id, name, nullif(description, '') as description
        from tags
        order by tag_id
        """,
    )
    pair_rows = duckdb_rows(
        source_db,
        """
        select pair_id, qid, tag_id
        from pairs
        order by pair_id
        """,
    )
    ref_rows = duckdb_rows(
        source_db,
        """
        select pair_id, ref_id
        from pair_refs
        order by pair_id, ref_id
        """,
    )

    pair_refs: defaultdict[int, list[int]] = defaultdict(list)
    for row in ref_rows:
        pair_refs[int(row["pair_id"])].append(int(row["ref_id"]))

    return SourceData(
        tags={
            int(row["tag_id"]): SourceTag(
                tag_id=int(row["tag_id"]),
                name=str(row["name"]),
                description=row["description"],
            )
            for row in tag_rows
        },
        pairs=[
            SourcePair(
                pair_id=int(row["pair_id"]),
                qid=str(row["qid"]),
                tag_id=int(row["tag_id"]),
            )
            for row in pair_rows
        ],
        pair_refs={
            pair_id: tuple(values)
            for pair_id, values in pair_refs.items()
        },
    )


def parse_tag_name(name: str) -> ParsedTag:
    if "__" in name:
        parts = name.split("__")
        prefix = parts[0]
        relation_object = parts[1] if len(parts) > 1 else ""
        link_kind = relation_link_kind(prefix)
        if link_kind is not None:
            target_qid = relation_object if QID_RE.fullmatch(relation_object) else None
            return ParsedTag(
                tag_kind=TAG_KIND_LEGACY_RELATION_TEXT,
                namespace=prefix,
                value="__".join(parts[1:]) or None,
                relation_prefix=prefix,
                relation_object=relation_object or None,
                target_qid=target_qid,
                link_kind=link_kind,
                target_kind=relation_target_kind(prefix),
            )

    if ":" in name:
        namespace, value = name.split(":", 1)
        if namespace and value:
            return ParsedTag(
                tag_kind=TAG_KIND_NAMESPACED,
                namespace=namespace,
                value=value,
            )

    return ParsedTag(tag_kind=TAG_KIND_PLAIN)


def relation_link_kind(prefix: str) -> int | None:
    if prefix.startswith("adapted_from_"):
        return LINK_KIND_ADAPTED_FROM
    if prefix.startswith("influence_"):
        return LINK_KIND_INFLUENCED_BY
    if prefix.startswith("influenced_"):
        return LINK_KIND_INFLUENCED
    return None


def relation_target_kind(prefix: str) -> int:
    if prefix.startswith("adapted_from_"):
        target_type = prefix.removeprefix("adapted_from_")
    elif prefix.startswith("influence_"):
        target_type = prefix.removeprefix("influence_")
    elif prefix.startswith("influenced_"):
        target_type = prefix.removeprefix("influenced_")
    else:
        return ENTITY_KIND_UNKNOWN

    if target_type in {"person", "writer", "director", "artist"}:
        return ENTITY_KIND_PERSON
    if target_type == "genre":
        return ENTITY_KIND_GENRE
    if target_type == "film":
        return ENTITY_KIND_FILM
    if target_type == "work":
        return ENTITY_KIND_WORK
    return ENTITY_KIND_UNKNOWN


def parse_wikidata_date(value: Any) -> tuple[str, int] | None:
    if not isinstance(value, dict):
        return None
    raw_time = value.get("time")
    precision = value.get("precision")
    if not isinstance(raw_time, str) or not isinstance(precision, int):
        return None

    match = WIKIDATA_TIME_RE.match(raw_time)
    if not match or match.group("sign") == "-":
        return None

    year = int(match.group("year"))
    if year <= 0:
        return None
    month = max(int(match.group("month")), 1)
    day = max(int(match.group("day")), 1)

    if precision >= 11:
        return f"{year:04d}-{month:02d}-{day:02d}", 3
    if precision == 10:
        return f"{year:04d}-{month:02d}-01", 2
    if precision == 9:
        return f"{year:04d}-01-01", 1
    return None


def best_date(claims: dict[str, Any]) -> tuple[str | None, int]:
    candidates: list[tuple[str, int]] = []
    for pid in DATE_CLAIM_PIDS:
        values = claims.get(pid)
        if not isinstance(values, list):
            continue
        for value in values:
            parsed = parse_wikidata_date(value)
            if parsed is not None:
                candidates.append(parsed)

    if not candidates:
        return None, 0
    return min(candidates, key=lambda item: (item[0], -item[1]))


def first_string(values: Any) -> str | None:
    if not isinstance(values, list):
        return None
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def title_from_claims(claims: dict[str, Any]) -> str:
    for pid in TITLE_CLAIM_PIDS:
        values = claims.get(pid)
        if not isinstance(values, list):
            continue

        text_values: list[tuple[int, str]] = []
        for index, value in enumerate(values):
            if isinstance(value, dict):
                text = value.get("text")
                lang = value.get("lang")
                if isinstance(text, str) and text:
                    rank = 0 if lang == "en" else 1 if lang == "mul" else 2 + index
                    text_values.append((rank, text))
            elif isinstance(value, str) and value:
                text_values.append((10 + index, value))

        if text_values:
            return min(text_values, key=lambda item: item[0])[1]
    return ""


def kind_from_layers(layers: Any) -> int:
    if not isinstance(layers, list):
        return ENTITY_KIND_UNKNOWN
    layer_set = {value for value in layers if isinstance(value, str)}
    if "film" in layer_set:
        return ENTITY_KIND_FILM
    if "music_album" in layer_set or "musical_work" in layer_set:
        return ENTITY_KIND_MUSIC_RELEASE
    if "video_game" in layer_set:
        return ENTITY_KIND_GAME
    if layer_set:
        return ENTITY_KIND_WORK
    return ENTITY_KIND_UNKNOWN


def qid_values(values: Any) -> Iterable[str]:
    if not isinstance(values, list):
        return ()
    return (
        value
        for value in values
        if isinstance(value, str) and QID_RE.fullmatch(value)
    )


def refs_from_claims(qid: str, claims: dict[str, Any]) -> tuple[tuple[int, str], ...]:
    refs: list[tuple[int, str]] = [(REF_KIND_WIKIDATA, qid)]

    imdb = first_string(claims.get("P345"))
    if imdb and imdb.startswith("tt"):
        refs.append((REF_KIND_IMDB, imdb))

    tmdb = first_string(claims.get("P4947")) or first_string(claims.get("P4983"))
    if tmdb:
        refs.append((REF_KIND_TMDB, tmdb))

    musicbrainz = (
        first_string(claims.get("P436"))
        or first_string(claims.get("P435"))
        or first_string(claims.get("P966"))
        or first_string(claims.get("P434"))
    )
    if musicbrainz:
        refs.append((REF_KIND_MUSICBRAINZ, musicbrainz))

    discogs = (
        first_string(claims.get("P1954"))
        or first_string(claims.get("P2205"))
        or first_string(claims.get("P2206"))
        or first_string(claims.get("P1953"))
    )
    if discogs:
        refs.append((REF_KIND_DISCOGS, discogs))

    deduped: dict[int, str] = {}
    for ref_kind, value in refs:
        deduped.setdefault(ref_kind, value)
    return tuple(sorted(deduped.items()))


def links_from_claims(claims: dict[str, Any]) -> tuple[LinkSeed, ...]:
    links: dict[tuple[str, int], LinkSeed] = {}

    for link_kind, pids in CLAIM_LINK_KINDS.items():
        for pid in pids:
            target_kind = ASSOCIATED_CLAIM_TARGET_KINDS.get(pid, ENTITY_KIND_UNKNOWN)
            if link_kind == LINK_KIND_ADAPTED_FROM:
                target_kind = ENTITY_KIND_WORK
            for qid in qid_values(claims.get(pid)):
                links[(qid, link_kind)] = LinkSeed(
                    target_qid=qid,
                    link_kind=link_kind,
                    target_kind=target_kind,
                )

    return tuple(
        links[key]
        for key in sorted(links, key=lambda item: (item[1], qid_sort_key(item[0])))
    )


def metadata_from_layer_row(row: dict[str, Any]) -> EntityMetadata:
    claims = row.get("claims")
    if not isinstance(claims, dict):
        claims = {}

    qid = row.get("id")
    if not isinstance(qid, str):
        qid = ""

    release_date, date_precision = best_date(claims)
    return EntityMetadata(
        label=title_from_claims(claims),
        entity_kind=kind_from_layers(row.get("layers")),
        release_date=release_date,
        date_precision=date_precision,
        image_ref=first_string(claims.get("P18")),
        refs=refs_from_claims(qid, claims) if qid else (),
        links=links_from_claims(claims),
    )


def scan_layer_metadata(
    layer_paths: Iterable[Path],
    wanted_qids: set[str],
) -> dict[str, EntityMetadata]:
    remaining = set(wanted_qids)
    metadata: dict[str, EntityMetadata] = {}
    if not remaining:
        return metadata

    for path in layer_paths:
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            for raw in handle:
                try:
                    row = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                qid = row.get("id")
                if not isinstance(qid, str) or qid not in remaining:
                    continue
                metadata[qid] = metadata_from_layer_row(row)
                remaining.remove(qid)
                if not remaining:
                    return metadata
    return metadata


def label_from_id_map_row(row: dict[str, Any]) -> str:
    labels = row.get("labels")
    if not isinstance(labels, dict):
        return ""
    for language in ("en", "mul", "de", "ru"):
        value = labels.get(language)
        if isinstance(value, str) and value:
            return value
    for value in labels.values():
        if isinstance(value, str) and value:
            return value
    return ""


def load_id_map_labels(path: Path | None, wanted_qids: set[str]) -> dict[str, str]:
    if path is None or not path.is_file() or not wanted_qids:
        return {}

    remaining = set(wanted_qids)
    labels: dict[str, str] = {}

    with path.open("rb") as handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            qid = row.get("id")
            if not isinstance(qid, str) or qid not in remaining:
                continue
            label = label_from_id_map_row(row)
            if label:
                labels[qid] = label
            remaining.remove(qid)
            if not remaining:
                break

    return labels


def assign_entity_ids(catalog_qids: set[str], secondary_qids: set[str]) -> dict[str, int]:
    qids = sorted(catalog_qids, key=qid_sort_key)
    qids.extend(
        qid
        for qid in sorted(secondary_qids, key=qid_sort_key)
        if qid not in catalog_qids
    )
    return {qid: index + 1 for index, qid in enumerate(qids)}


def migrate_art_database(
    *,
    source_db: Path,
    target_db: Path,
    layer_paths: Iterable[Path] = (),
    id_map_path: Path | None = None,
    replace: bool = False,
) -> MigrationStats:
    target_artifacts = [
        target_db,
        Path(f"{target_db}-wal"),
        Path(f"{target_db}-shm"),
    ]
    if any(path.exists() for path in target_artifacts):
        if not replace:
            raise FileExistsError(f"target database already exists: {target_db}")
        remove_sqlite_database(target_db)

    source = load_source_data(source_db)
    parsed_tags = {
        tag_id: parse_tag_name(tag.name)
        for tag_id, tag in source.tags.items()
    }

    catalog_qids = {
        pair.qid
        for pair in source.pairs
        if QID_RE.fullmatch(pair.qid)
    }
    relation_target_qids = {
        parsed.target_qid
        for parsed in parsed_tags.values()
        if parsed.target_qid is not None
    }

    metadata = scan_layer_metadata(
        layer_paths,
        catalog_qids | relation_target_qids,
    )

    inferred_target_kinds: dict[str, int] = {}
    claim_target_qids: set[str] = set()
    for qid in catalog_qids:
        for link in metadata.get(qid, EntityMetadata()).links:
            claim_target_qids.add(link.target_qid)
            inferred_target_kinds.setdefault(link.target_qid, link.target_kind)

    for parsed in parsed_tags.values():
        if parsed.target_qid is not None:
            inferred_target_kinds.setdefault(parsed.target_qid, parsed.target_kind)

    secondary_qids = relation_target_qids | claim_target_qids
    all_qids = catalog_qids | secondary_qids
    missing_label_qids = {
        qid
        for qid in all_qids
        if not metadata.get(qid, EntityMetadata()).label
    }
    id_map_labels = load_id_map_labels(id_map_path, missing_label_qids)
    entity_ids = assign_entity_ids(catalog_qids, secondary_qids)

    db = connect_art(target_db)
    try:
        db.execute("begin")
        _insert_entities(
            db,
            entity_ids=entity_ids,
            catalog_qids=catalog_qids,
            metadata=metadata,
            id_map_labels=id_map_labels,
            inferred_target_kinds=inferred_target_kinds,
        )
        _insert_tags(db, source.tags, parsed_tags)
        _insert_entity_refs(db, entity_ids, metadata)
        stats = _insert_pairs_and_links(
            db,
            source=source,
            parsed_tags=parsed_tags,
            entity_ids=entity_ids,
            metadata=metadata,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return stats


def _insert_entities(
    db: sqlite3.Connection,
    *,
    entity_ids: dict[str, int],
    catalog_qids: set[str],
    metadata: dict[str, EntityMetadata],
    id_map_labels: dict[str, str],
    inferred_target_kinds: dict[str, int],
) -> None:
    rows = []
    for qid, entity_id in sorted(entity_ids.items(), key=lambda item: item[1]):
        item = metadata.get(qid, EntityMetadata())
        entity_kind = item.entity_kind
        if entity_kind == ENTITY_KIND_UNKNOWN:
            entity_kind = inferred_target_kinds.get(qid, ENTITY_KIND_UNKNOWN)
        label = item.label or id_map_labels.get(qid) or qid
        rows.append(
            (
                entity_id,
                label,
                entity_kind,
                item.release_date,
                item.date_precision,
                1 if qid in catalog_qids else 0,
                item.image_ref,
            )
        )

    db.executemany(
        """
        insert into entities(
            entity_id,
            label,
            entity_kind,
            release_date,
            date_precision,
            is_catalogued,
            image_ref
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_tags(
    db: sqlite3.Connection,
    tags: dict[int, SourceTag],
    parsed_tags: dict[int, ParsedTag],
) -> None:
    db.executemany(
        """
        insert into tags(tag_id, name, description, tag_kind, namespace, value)
        values (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                tag.tag_id,
                tag.name,
                tag.description,
                parsed_tags[tag.tag_id].tag_kind,
                parsed_tags[tag.tag_id].namespace,
                parsed_tags[tag.tag_id].value,
            )
            for tag in tags.values()
        ],
    )


def _insert_entity_refs(
    db: sqlite3.Connection,
    entity_ids: dict[str, int],
    metadata: dict[str, EntityMetadata],
) -> None:
    rows: list[tuple[int, int, str]] = []
    for qid, entity_id in entity_ids.items():
        rows.append((entity_id, REF_KIND_WIKIDATA, qid))
        for ref_kind, ref_value in metadata.get(qid, EntityMetadata()).refs:
            if ref_kind == REF_KIND_WIKIDATA:
                continue
            rows.append((entity_id, ref_kind, ref_value))

    db.executemany(
        """
        insert into entity_refs(entity_id, ref_kind, ref_value)
        values (?, ?, ?)
        on conflict do nothing
        """,
        rows,
    )


def _insert_pairs_and_links(
    db: sqlite3.Connection,
    *,
    source: SourceData,
    parsed_tags: dict[int, ParsedTag],
    entity_ids: dict[str, int],
    metadata: dict[str, EntityMetadata],
) -> MigrationStats:
    tag_ref_rows: list[tuple[int, int, int]] = []
    link_ref_rows: list[tuple[int, int, int, int]] = []

    for pair in source.pairs:
        source_entity_id = entity_ids.get(pair.qid)
        if source_entity_id is None:
            continue
        parsed = parsed_tags[pair.tag_id]
        if parsed.target_qid is not None and parsed.link_kind is not None:
            target_entity_id = entity_ids.get(parsed.target_qid)
            if target_entity_id is None:
                continue
            db.execute(
                """
                insert into entity_links(
                    source_entity_id,
                    target_entity_id,
                    link_kind,
                    weight,
                    polarity,
                    legacy_tag_id
                )
                values (?, ?, ?, 50, 0, ?)
                on conflict(source_entity_id, target_entity_id, link_kind)
                do nothing
                """,
                (
                    source_entity_id,
                    target_entity_id,
                    parsed.link_kind,
                    pair.tag_id,
                ),
            )
            for ref_id in source.pair_refs.get(pair.pair_id, ()):
                link_ref_rows.append(
                    (source_entity_id, target_entity_id, parsed.link_kind, ref_id)
                )
            continue

        db.execute(
            """
            insert into entity_tags(entity_id, tag_id, weight, polarity)
            values (?, ?, 50, 0)
            on conflict(entity_id, tag_id) do nothing
            """,
            (source_entity_id, pair.tag_id),
        )
        for ref_id in source.pair_refs.get(pair.pair_id, ()):
            tag_ref_rows.append((source_entity_id, pair.tag_id, ref_id))

    for qid, item in metadata.items():
        source_entity_id = entity_ids.get(qid)
        if source_entity_id is None:
            continue
        for link in item.links:
            target_entity_id = entity_ids.get(link.target_qid)
            if target_entity_id is None or target_entity_id == source_entity_id:
                continue
            db.execute(
                """
                insert into entity_links(
                    source_entity_id,
                    target_entity_id,
                    link_kind,
                    weight,
                    polarity,
                    legacy_tag_id
                )
                values (?, ?, ?, 25, 0, null)
                on conflict(source_entity_id, target_entity_id, link_kind)
                do nothing
                """,
                (source_entity_id, target_entity_id, link.link_kind),
            )

    db.executemany(
        """
        insert into entity_tag_refs(entity_id, tag_id, ref_id)
        values (?, ?, ?)
        on conflict do nothing
        """,
        tag_ref_rows,
    )
    db.executemany(
        """
        insert into entity_link_refs(
            source_entity_id,
            target_entity_id,
            link_kind,
            ref_id
        )
        values (?, ?, ?, ?)
        on conflict do nothing
        """,
        link_ref_rows,
    )

    row = db.execute(
        """
        select
            (select count(*) from entities) as entities,
            (select count(*) from entities where is_catalogued = 1) as catalogued,
            (select count(*) from entities where is_catalogued = 0) as secondary,
            (select count(*) from tags) as tags,
            (select count(*) from entity_tags) as entity_tags,
            (select count(*) from entity_links) as entity_links,
            (select count(*) from entity_tag_refs) as entity_tag_refs,
            (select count(*) from entity_link_refs) as entity_link_refs
        """
    ).fetchone()

    return MigrationStats(
        entities=int(row["entities"]),
        catalogued_entities=int(row["catalogued"]),
        secondary_entities=int(row["secondary"]),
        tags=int(row["tags"]),
        entity_tags=int(row["entity_tags"]),
        entity_links=int(row["entity_links"]),
        entity_tag_refs=int(row["entity_tag_refs"]),
        entity_link_refs=int(row["entity_link_refs"]),
    )


def settings_with_defaults(value: dict[str, Any] | None = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    recommendation = source.get("recommendation")
    if not isinstance(recommendation, dict):
        recommendation = {}

    defaults = DEFAULT_SETTINGS["recommendation"]
    merged = {
        "recommendation": {
            "likeWeight": float(
                recommendation.get("likeWeight", defaults["likeWeight"])
            ),
            "dislikeWeight": float(
                recommendation.get("dislikeWeight", defaults["dislikeWeight"])
            ),
            "limit": int(recommendation.get("limit", defaults["limit"])),
        }
    }
    if merged["recommendation"]["likeWeight"] < 0:
        merged["recommendation"]["likeWeight"] = defaults["likeWeight"]
    if merged["recommendation"]["dislikeWeight"] < 0:
        merged["recommendation"]["dislikeWeight"] = defaults["dislikeWeight"]
    if merged["recommendation"]["limit"] < 1:
        merged["recommendation"]["limit"] = defaults["limit"]
    return merged


def load_settings(path: Path | None = None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return settings_with_defaults()
    with path.open("r", encoding="utf-8") as handle:
        return settings_with_defaults(json.load(handle))


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = settings_with_defaults(settings)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def export_static_data(
    db_path: Path,
    output_dir: Path,
    settings_path: Path | None = None,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db = connect_art(db_path)
    try:
        tags = _export_tags(db)
        entities_lookup = _export_entities_lookup(db)
        catalog = _export_catalog(db)
    finally:
        db.close()

    settings = load_settings(settings_path)
    write_json(output_dir / "catalog.json", catalog)
    write_json(output_dir / "tags.json", tags)
    write_json(output_dir / "entities-lookup.json", entities_lookup)
    write_json(output_dir / "settings.json", settings)
    for stale_name in ("entity-tags.json", "entity-links.json"):
        stale_path = output_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()

    return {
        "catalog": len(catalog),
        "tags": len(tags),
        "entities_lookup": len(entities_lookup),
        "settings": 1,
    }


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def _export_tags(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        select tag_id, name, description, tag_kind, namespace, value
        from tags
        order by name collate nocase
        """
    ).fetchall()
    return [
        {
            "id": row["tag_id"],
            "name": row["name"],
            "description": row["description"],
            "kind": row["tag_kind"],
            "namespace": row["namespace"],
            "value": row["value"],
        }
        for row in rows
    ]


def _export_entity_tags(db: sqlite3.Connection) -> list[list[int]]:
    rows = db.execute(
        """
        select entity_id, tag_id, weight, polarity
        from entity_tags
        order by entity_id, tag_id
        """
    ).fetchall()
    return [
        [row["entity_id"], row["tag_id"], row["weight"], row["polarity"]]
        for row in rows
    ]


def _export_entity_links(db: sqlite3.Connection) -> list[list[int]]:
    rows = db.execute(
        """
        select source_entity_id, target_entity_id, link_kind, weight, polarity
        from entity_links
        order by source_entity_id, target_entity_id, link_kind
        """
    ).fetchall()
    return [
        [
            row["source_entity_id"],
            row["target_entity_id"],
            row["link_kind"],
            row["weight"],
            row["polarity"],
        ]
        for row in rows
    ]


def _export_entities_lookup(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        """
        select entity_id, label, entity_kind, is_catalogued
        from entities
        order by entity_id
        """
    ).fetchall()
    return {
        str(row["entity_id"]): {
            "label": row["label"],
            "kind": row["entity_kind"],
            "catalogued": bool(row["is_catalogued"]),
        }
        for row in rows
    }


def _export_catalog(db: sqlite3.Connection) -> list[dict[str, Any]]:
    catalog_rows = db.execute(
        """
        select entity_id, label, entity_kind, release_date, date_precision, image_ref
        from entities
        where is_catalogued = 1
        order by
            case when release_date is null then 1 else 0 end,
            release_date,
            label collate nocase,
            entity_id
        """
    ).fetchall()

    refs = _group_refs(db)
    tags = _group_tags(db)
    links = _group_links(db)

    return [
        {
            "id": row["entity_id"],
            "label": row["label"],
            "kind": row["entity_kind"],
            "date": row["release_date"],
            "datePrecision": row["date_precision"],
            "image": row["image_ref"],
            "refs": refs.get(row["entity_id"], []),
            "tags": tags.get(row["entity_id"], []),
            "links": links.get(row["entity_id"], []),
        }
        for row in catalog_rows
    ]


def _group_refs(db: sqlite3.Connection) -> dict[int, list[list[str]]]:
    rows = db.execute(
        """
        select entity_id, ref_kind, ref_value
        from entity_refs
        order by entity_id, ref_kind
        """
    ).fetchall()
    grouped: defaultdict[int, list[list[str]]] = defaultdict(list)
    for row in rows:
        grouped[row["entity_id"]].append(
            [REF_KIND_LABELS.get(row["ref_kind"], str(row["ref_kind"])), row["ref_value"]]
        )
    return dict(grouped)


def _group_tags(db: sqlite3.Connection) -> dict[int, list[list[int]]]:
    rows = db.execute(
        """
        select entity_id, tag_id, weight, polarity
        from entity_tags
        order by entity_id, weight desc, tag_id
        """
    ).fetchall()
    grouped: defaultdict[int, list[list[int]]] = defaultdict(list)
    for row in rows:
        grouped[row["entity_id"]].append(
            [row["tag_id"], row["weight"], row["polarity"]]
        )
    return dict(grouped)


def _group_links(db: sqlite3.Connection) -> dict[int, list[list[int]]]:
    rows = db.execute(
        """
        select source_entity_id, target_entity_id, link_kind, weight, polarity
        from entity_links
        order by source_entity_id, weight desc, target_entity_id, link_kind
        """
    ).fetchall()
    grouped: defaultdict[int, list[list[int]]] = defaultdict(list)
    for row in rows:
        grouped[row["source_entity_id"]].append(
            [
                row["target_entity_id"],
                row["link_kind"],
                row["weight"],
                row["polarity"],
            ]
        )
    return dict(grouped)
