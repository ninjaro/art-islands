from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .schema import DOMAIN_SCHEMA


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
    },
    "features": {
        "directConceptMultiplier": 1.0,
        "creatorMultiplier": 0.55,
        "directorMultiplier": 0.5,
        "authorMultiplier": 0.55,
        "producerMultiplier": 0.3,
        "performerMultiplier": 0.25,
        "organizationMultiplier": 0.2,
        "contentGuideMultiplier": 0.25,
    },
    "evolution": {
        "visibleChildrenPerNode": 4,
        "maxInitialRoots": 20,
        "groupingSimilarity": 0.25,
        "minimumSimilarity": 0.18,
        "minimumSharedFeatures": 2,
        "kindMismatchFactor": 0.6,
    },
    "islands": {
        "maxRecommendationNodes": 150,
        "maxInferredNeighborsPerNode": 8,
        "maxEdges": 500,
        "minimumSimilarity": 0.12,
    },
    "browse": {
        "defaultPageSize": 50,
        "pageSizeOptions": [25, 50, 100],
    },
}

INT_SETTING_KEYS = {
    "limit",
    "visibleChildrenPerNode",
    "maxInitialRoots",
    "minimumSharedFeatures",
    "maxRecommendationNodes",
    "maxInferredNeighborsPerNode",
    "maxEdges",
    "defaultPageSize",
}

LEGACY_SETTING_ALIASES = {
    "islands": {"maxNeighborsPerSeed": "maxInferredNeighborsPerNode"},
    "evolution": {"minimumSharedTags": "minimumSharedFeatures"},
}

QID_RE = re.compile(r"^Q[1-9][0-9]*$")
WIKIDATA_TIME_RE = re.compile(
    r"^(?P<sign>[+-])(?P<year>\d+)-(?P<month>\d{2})-(?P<day>\d{2})T"
)


ART_SCHEMA = DOMAIN_SCHEMA


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


def settings_with_defaults(value: dict[str, Any] | None = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    merged: dict[str, Any] = {}
    for section_name, defaults in DEFAULT_SETTINGS.items():
        raw_section = source.get(section_name)
        if not isinstance(raw_section, dict):
            raw_section = {}
        else:
            raw_section = dict(raw_section)
        for legacy, current in LEGACY_SETTING_ALIASES.get(section_name, {}).items():
            if current not in raw_section and legacy in raw_section:
                raw_section[current] = raw_section[legacy]
            raw_section.pop(legacy, None)
        section: dict[str, Any] = {}
        for key, default in defaults.items():
            raw = raw_section.get(key, default)
            if isinstance(default, list):
                parsed = default
                if isinstance(raw, list):
                    values = [entry for entry in raw if isinstance(entry, int) and entry > 0]
                    if values and len(values) == len(raw):
                        parsed = values
                section[key] = list(parsed)
                continue
            try:
                parsed = int(raw) if key in INT_SETTING_KEYS else float(raw)
            except (TypeError, ValueError):
                parsed = default
            if parsed < 0:
                parsed = default
            if key == "limit" and parsed < 1:
                parsed = default
            section[key] = parsed
        merged[section_name] = section
    browse = merged["browse"]
    if browse["defaultPageSize"] not in browse["pageSizeOptions"]:
        default_size = DEFAULT_SETTINGS["browse"]["defaultPageSize"]
        browse["defaultPageSize"] = (
            default_size if default_size in browse["pageSizeOptions"] else browse["pageSizeOptions"][0]
        )
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
    from .evolution import build_evolution_export

    output_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings(settings_path)
    db = connect_art(db_path)
    try:
        check = db.execute("pragma quick_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"database failed quick_check: {check}")
        evolution = build_evolution_export(db, settings)
    finally:
        db.close()

    write_json(output_dir / "settings.json", settings)
    write_json(output_dir / "evolution.json", evolution)
    for stale_name in (
        "catalog.json",
        "tags.json",
        "entities-lookup.json",
        "entity-tags.json",
        "entity-links.json",
    ):
        stale_path = output_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()

    return {
        "settings": 1,
        "evolution": len(evolution["nodes"]),
    }


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
