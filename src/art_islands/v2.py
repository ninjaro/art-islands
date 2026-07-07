from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .model import (
    DEFAULT_ART_LAYER_NAMES,
    ENTITY_KIND_FILM,
    ENTITY_KIND_GAME,
    ENTITY_KIND_GROUP,
    ENTITY_KIND_MUSIC_RELEASE,
    ENTITY_KIND_ORGANIZATION,
    ENTITY_KIND_PERSON,
    ENTITY_KIND_UNKNOWN,
    ENTITY_KIND_WORK,
    QID_RE,
    REF_KIND_DISCOGS,
    REF_KIND_IMDB,
    REF_KIND_MUSICBRAINZ,
    REF_KIND_TMDB,
    REF_KIND_WIKIDATA,
    connect_art,
    load_settings,
    parse_wikidata_date,
    write_json,
)
from .schema import MigrationError, migration_status, run_migrations


WORKSPACE_REL = Path("tools/db_v2_migration")
REPORT_NAMES = (
    "inventory.json",
    "current_database.json",
    "date_precision_before_after.tsv",
    "entity_type_distribution.tsv",
    "relation_type_distribution.tsv",
    "concept_classification.tsv",
    "unclassified_tags.tsv",
    "unresolved_entities.tsv",
    "external_identifier_coverage.tsv",
    "remote_requests.json",
    "conflicts.tsv",
    "validation_summary.json",
)

LOCAL_INPUTS = (
    "book.jsonl",
    "comics.jsonl",
    "film.jsonl",
    "id_map.slow.partial.jsonl",
    "music_album.jsonl",
    "musical_work.jsonl",
    "occupation_counts.tsv",
    "other_creative_work.jsonl",
    "painting.jsonl",
    "people.jsonl",
    "people_p106_selected_categories.tsv",
    "people_p106_selected_qids.txt",
    "people_selected_claims.jsonl.zst",
    "photograph.jsonl",
    "sculpture.jsonl",
    "summary.tsv",
    "taxonomy.sqlite",
    "television_series.jsonl",
    "used_ids.sqlite",
    "used_pids.txt",
    "used_qids.txt",
    "video_game.jsonl",
    "work_class_map.tsv",
)

ENTITY_TYPE_DEFINITIONS = (
    ("unknown", "unknown", "Unknown", "Unclassified entity."),
    ("film", "work", "Film", "Motion picture or film work."),
    ("television_series", "work", "Television series", "Television series."),
    ("music_album", "work", "Music album", "Album or release group."),
    ("musical_work", "work", "Musical work", "Song, composition, or recording."),
    ("book", "work", "Book", "Book or written work."),
    ("comics", "work", "Comics", "Comics work."),
    ("painting", "work", "Painting", "Painting."),
    ("sculpture", "work", "Sculpture", "Sculpture."),
    ("photograph", "work", "Photograph", "Photographic work."),
    ("video_game", "work", "Video game", "Video game."),
    ("other_creative_work", "work", "Other creative work", "Creative work not otherwise classified."),
    ("person", "person", "Person", "Human contributor or subject."),
    ("creative_group", "group", "Creative group", "Creative group."),
    ("music_group", "group", "Music group", "Music group."),
    ("band", "group", "Band", "Band."),
    ("organization", "organization", "Organization", "Organization."),
    ("company", "organization", "Company", "Company."),
    ("production_company", "organization", "Production company", "Production company."),
    ("film_studio", "organization", "Film studio", "Film studio."),
    ("record_label", "organization", "Record label", "Record label."),
    ("publisher", "organization", "Publisher", "Publisher."),
    ("broadcaster", "organization", "Broadcaster", "Broadcaster."),
    ("game_studio", "organization", "Game studio", "Game studio."),
    ("developer", "organization", "Developer", "Developer."),
    ("distributor", "organization", "Distributor", "Distributor."),
    ("genre", "concept", "Genre", "Genre concept."),
)

IDENTIFIER_SCHEMES = (
    ("wikidata", "Wikidata", None, r"^Q[1-9][0-9]*$", "https://www.wikidata.org/wiki/{value}"),
    ("imdb_title", "IMDb title", "work", r"^tt\d{6,10}$", "https://www.imdb.com/title/{value}/"),
    ("imdb_name", "IMDb name", "person", r"^nm\d{6,10}$", "https://www.imdb.com/name/{value}/"),
    ("imdb_company", "IMDb company", "organization", r"^co\d{6,10}$", "https://www.imdb.com/search/title/?companies={value}"),
    ("tmdb_movie", "TMDB movie", "work", r"^\d{1,12}$", "https://www.themoviedb.org/movie/{value}"),
    ("tmdb_tv", "TMDB TV", "work", r"^\d{1,12}$", "https://www.themoviedb.org/tv/{value}"),
    ("tmdb_person", "TMDB person", "person", r"^\d{1,12}$", "https://www.themoviedb.org/person/{value}"),
    ("musicbrainz_release", "MusicBrainz release", "work", None, "https://musicbrainz.org/release/{value}"),
    ("musicbrainz_release_group", "MusicBrainz release group", "work", None, "https://musicbrainz.org/release-group/{value}"),
    ("musicbrainz_recording", "MusicBrainz recording", "work", None, "https://musicbrainz.org/recording/{value}"),
    ("musicbrainz_work", "MusicBrainz work", "work", None, "https://musicbrainz.org/work/{value}"),
    ("musicbrainz_artist", "MusicBrainz artist", "person", None, "https://musicbrainz.org/artist/{value}"),
    ("discogs_release", "Discogs release", "work", r"^\d{1,12}$", "https://www.discogs.com/release/{value}"),
    ("discogs_master", "Discogs master", "work", r"^\d{1,12}$", "https://www.discogs.com/master/{value}"),
    ("discogs_artist", "Discogs artist", "person", r"^\d{1,12}$", "https://www.discogs.com/artist/{value}"),
)

RELATION_TYPES = (
    ("associated", "Associated", "legacy", "work", None, None),
    ("director", "Director", "contributor", "work", "person", None),
    ("screenwriter", "Screenwriter", "contributor", "work", "person", None),
    ("writer", "Writer", "contributor", "work", "person", None),
    ("author", "Author", "contributor", "work", "person", None),
    ("editor", "Editor", "contributor", "work", "person", None),
    ("illustrator", "Illustrator", "contributor", "work", "person", None),
    ("creator", "Creator", "contributor", "work", None, None),
    ("producer", "Producer", "contributor", "work", None, None),
    ("executive_producer", "Executive producer", "contributor", "work", None, None),
    ("actor", "Actor", "contributor", "work", "person", None),
    ("voice_actor", "Voice actor", "contributor", "work", "person", None),
    ("cast_member", "Cast member", "contributor", "work", "person", None),
    ("character", "Character", "subject", "work", None, None),
    ("composer", "Composer", "contributor", "work", "person", None),
    ("lyricist", "Lyricist", "contributor", "work", "person", None),
    ("performer", "Performer", "contributor", "work", None, None),
    ("music_artist", "Music artist", "contributor", "work", None, None),
    ("photographer", "Photographer", "contributor", "work", "person", None),
    ("painter", "Painter", "contributor", "work", "person", None),
    ("sculptor", "Sculptor", "contributor", "work", "person", None),
    ("designer", "Designer", "contributor", "work", "person", None),
    ("developer", "Developer", "contributor", "work", None, None),
    ("publisher", "Publisher", "organization", "work", "organization", None),
    ("record_label", "Record label", "organization", "work", "organization", None),
    ("production_company", "Production company", "organization", "work", "organization", None),
    ("film_studio", "Film studio", "organization", "work", "organization", None),
    ("broadcaster", "Broadcaster", "organization", "work", "organization", None),
    ("distributor", "Distributor", "organization", "work", "organization", None),
    ("platform", "Platform", "platform", "work", None, None),
    ("based_on", "Based on", "source", "work", "work", None),
    ("adapted_from", "Adapted from", "source", "work", "work", None),
    ("influenced_by", "Influenced by", "influence", "work", None, "influenced"),
    ("influenced", "Influenced", "influence", "work", None, "influenced_by"),
    ("inspired_by", "Inspired by", "influence", "work", None, None),
    ("depicts", "Depicts", "subject", "work", None, None),
    ("main_subject", "Main subject", "subject", "work", None, None),
)

CONCEPT_CATEGORIES = (
    "genre",
    "keyword",
    "theme",
    "subject",
    "style",
    "movement",
    "mood",
    "motif",
    "setting",
    "trope",
    "audience",
    "format",
    "technique",
    "language",
    "country",
    "period",
    "franchise",
    "other",
)

ADVISORY_CATEGORIES = (
    "violence",
    "graphic_violence",
    "blood",
    "gore",
    "profanity",
    "sexual_content",
    "nudity",
    "frightening_scenes",
    "drug_use",
    "alcohol",
    "smoking",
    "self_harm",
    "suicide",
    "abuse",
    "torture",
    "discrimination",
    "hate_content",
    "flashing_lights",
    "loud_sounds",
    "animal_harm",
    "death",
    "medical_content",
    "body_horror",
)

MEASUREMENT_TYPES = (
    ("duration", "Duration", "seconds"),
    ("height", "Height", "millimeters"),
    ("width", "Width", "millimeters"),
    ("depth", "Depth", "millimeters"),
    ("thickness", "Thickness", "millimeters"),
    ("diameter", "Diameter", "millimeters"),
    ("weight", "Weight", "grams"),
    ("page_count", "Page count", "pages"),
    ("track_count", "Track count", "tracks"),
    ("episode_count", "Episode count", "episodes"),
    ("season_count", "Season count", "seasons"),
)

DATA_SOURCES = (
    ("legacy_database", "Legacy Art Islands database", "sqlite", None),
    ("local_layer", "Local Wikidata layer", "jsonl", None),
    ("local_people_claims", "Local selected people claims", "jsonl.zst", None),
    ("local_taxonomy", "Local taxonomy database", "sqlite", None),
    ("wikidata_api", "Wikidata API", "remote_api", "https://www.wikidata.org/"),
    ("manual", "Manual correction", "manual", None),
    ("heuristic", "Heuristic rule", "heuristic", None),
    ("future_imdb", "Future IMDb source", "future", "https://www.imdb.com/"),
    ("future_tmdb", "Future TMDB source", "future", "https://www.themoviedb.org/"),
    ("future_musicbrainz", "Future MusicBrainz source", "future", "https://musicbrainz.org/"),
    ("future_discogs", "Future Discogs source", "future", "https://www.discogs.com/"),
)

DATE_TYPES = (
    "publication",
    "first_publication",
    "release",
    "premiere",
    "first_performance",
    "broadcast_start",
    "broadcast_end",
    "creation",
    "inception",
    "start",
    "end",
    "point_in_time",
)

WORK_LAYER_ORDER = {
    layer: index
    for index, layer in enumerate(
        (
            "film",
            "television_series",
            "music_album",
            "musical_work",
            "book",
            "comics",
            "painting",
            "sculpture",
            "photograph",
            "video_game",
            "other_creative_work",
            "people",
        )
    )
}

LAYER_TYPE_CODES = {
    "film": "film",
    "television_series": "television_series",
    "music_album": "music_album",
    "musical_work": "musical_work",
    "book": "book",
    "comics": "comics",
    "painting": "painting",
    "sculpture": "sculpture",
    "photograph": "photograph",
    "video_game": "video_game",
    "other_creative_work": "other_creative_work",
    "people": "person",
}

TYPE_CODE_TO_ENTITY_KIND = {
    "unknown": ENTITY_KIND_UNKNOWN,
    "film": ENTITY_KIND_FILM,
    "television_series": ENTITY_KIND_WORK,
    "music_album": ENTITY_KIND_MUSIC_RELEASE,
    "musical_work": ENTITY_KIND_MUSIC_RELEASE,
    "book": ENTITY_KIND_WORK,
    "comics": ENTITY_KIND_WORK,
    "painting": ENTITY_KIND_WORK,
    "sculpture": ENTITY_KIND_WORK,
    "photograph": ENTITY_KIND_WORK,
    "video_game": ENTITY_KIND_GAME,
    "other_creative_work": ENTITY_KIND_WORK,
    "person": ENTITY_KIND_PERSON,
    "creative_group": ENTITY_KIND_GROUP,
    "music_group": ENTITY_KIND_GROUP,
    "band": ENTITY_KIND_GROUP,
    "organization": ENTITY_KIND_ORGANIZATION,
    "company": ENTITY_KIND_ORGANIZATION,
    "production_company": ENTITY_KIND_ORGANIZATION,
    "film_studio": ENTITY_KIND_ORGANIZATION,
    "record_label": ENTITY_KIND_ORGANIZATION,
    "publisher": ENTITY_KIND_ORGANIZATION,
    "broadcaster": ENTITY_KIND_ORGANIZATION,
    "game_studio": ENTITY_KIND_ORGANIZATION,
    "developer": ENTITY_KIND_ORGANIZATION,
    "distributor": ENTITY_KIND_ORGANIZATION,
}

DATE_PROPERTY_TYPES = {
    "P577": "release",
    "P571": "inception",
    "P580": "start",
    "P582": "end",
    "P585": "point_in_time",
    "P1191": "first_performance",
    "P1619": "premiere",
}

PRIMARY_DATE_PRIORITY = {
    "film": ("release", "premiere", "publication", "inception", "point_in_time"),
    "television_series": ("broadcast_start", "release", "start", "inception", "point_in_time"),
    "music_album": ("release", "publication", "inception", "point_in_time"),
    "musical_work": ("publication", "release", "first_performance", "creation", "inception", "point_in_time"),
    "book": ("publication", "release", "inception", "point_in_time"),
    "comics": ("publication", "release", "inception", "point_in_time"),
    "painting": ("creation", "inception", "point_in_time"),
    "sculpture": ("creation", "inception", "point_in_time"),
    "photograph": ("creation", "inception", "point_in_time"),
    "video_game": ("release", "publication", "inception", "point_in_time"),
    "other_creative_work": ("publication", "release", "creation", "inception", "point_in_time"),
}

RELATION_PROPERTY_CODES = {
    "P57": "director",
    "P58": "screenwriter",
    "P50": "author",
    "P98": "editor",
    "P110": "illustrator",
    "P161": "cast_member",
    "P725": "voice_actor",
    "P162": "producer",
    "P170": "creator",
    "P175": "performer",
    "P86": "composer",
    "P676": "lyricist",
    "P178": "developer",
    "P123": "publisher",
    "P264": "record_label",
    "P272": "production_company",
    "P449": "broadcaster",
    "P750": "distributor",
    "P400": "platform",
    "P144": "adapted_from",
    "P737": "influenced_by",
    "P941": "inspired_by",
    "P180": "depicts",
    "P921": "main_subject",
}

RELATION_TARGET_TYPE_CODES = {
    "director": "person",
    "screenwriter": "person",
    "writer": "person",
    "author": "person",
    "editor": "person",
    "illustrator": "person",
    "actor": "person",
    "voice_actor": "person",
    "cast_member": "person",
    "producer": "person",
    "composer": "person",
    "lyricist": "person",
    "photographer": "person",
    "painter": "person",
    "sculptor": "person",
    "performer": "creative_group",
    "music_artist": "music_group",
    "developer": "organization",
    "publisher": "publisher",
    "record_label": "record_label",
    "production_company": "production_company",
    "film_studio": "film_studio",
    "broadcaster": "broadcaster",
    "distributor": "distributor",
    "platform": "organization",
    "based_on": "other_creative_work",
    "adapted_from": "other_creative_work",
}

CONCEPT_PROPERTY_CATEGORIES = {
    "P136": ("genre", 80, 0.9),
    "P135": ("movement", 75, 0.9),
    "P921": ("subject", 70, 0.85),
    "P180": ("subject", 70, 0.85),
    "P407": ("language", 60, 0.85),
    "P495": ("country", 60, 0.85),
    "P840": ("setting", 65, 0.8),
    "P179": ("franchise", 65, 0.8),
    "P361": ("franchise", 60, 0.75),
}

IDENTIFIER_PROPERTY_SCHEMES = {
    "P4947": ("tmdb_movie",),
    "P4983": ("tmdb_tv",),
    "P436": ("musicbrainz_release_group",),
    "P435": ("musicbrainz_work",),
    "P966": ("musicbrainz_recording",),
    "P434": ("musicbrainz_artist",),
    "P1954": ("discogs_master",),
    "P2205": ("discogs_release",),
    "P2206": ("discogs_artist",),
    "P1953": ("discogs_artist",),
}

MEASUREMENT_PROPERTY_TYPES = {
    "P2047": "duration",
    "P2048": "height",
    "P2049": "width",
    "P2610": "thickness",
    "P2386": "diameter",
    "P2067": "weight",
    "P1104": "page_count",
    "P1113": "episode_count",
    "P2437": "season_count",
}

DIMENSION_UNIT_MULTIPLIERS = {
    "Q11573": ("millimeters", 1000.0),  # metre
    "Q174728": ("millimeters", 10.0),  # centimetre
    "Q174789": ("millimeters", 1.0),  # millimetre
}

DURATION_UNIT_MULTIPLIERS = {
    "Q11574": ("seconds", 1.0),
    "Q7727": ("seconds", 60.0),
    "Q25235": ("seconds", 3600.0),
}

WEIGHT_UNIT_MULTIPLIERS = {
    "Q11570": ("grams", 1000.0),
    "Q41803": ("grams", 1.0),
}


@dataclass(frozen=True)
class MigrationPaths:
    project_root: Path
    workspace: Path
    cache: Path
    checkpoints: Path
    reports: Path
    scripts: Path
    sql: Path
    tests: Path


def workspace_paths(project_root: Path) -> MigrationPaths:
    workspace = project_root / WORKSPACE_REL
    return MigrationPaths(
        project_root=project_root,
        workspace=workspace,
        cache=workspace / "cache",
        checkpoints=workspace / "checkpoints",
        reports=workspace / "reports",
        scripts=workspace / "scripts",
        sql=workspace / "sql",
        tests=workspace / "tests",
    )


def ensure_workspace(project_root: Path) -> MigrationPaths:
    paths = workspace_paths(project_root)
    for path in (
        paths.workspace,
        paths.cache,
        paths.checkpoints,
        paths.reports,
        paths.scripts,
        paths.sql,
        paths.tests,
    ):
        path.mkdir(parents=True, exist_ok=True)
    readme = paths.workspace / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    "# Art Islands DB v2 Migration Workspace",
                    "",
                    "This directory contains one-off migration tooling, reports,",
                    "checkpoints, cache schemas, and reproduction commands for the",
                    "offline-first Art Islands database v2 migration.",
                    "",
                    "Useful commands:",
                    "",
                    "```sh",
                    "art-islands db-v2 inventory",
                    "art-islands db-v2 migrate",
                    "art-islands db-v2 export",
                    "art-islands db-v2 validate",
                    "```",
                    "",
                    "Large generated caches and checkpoints are ignored by git.",
                    "Source files under `../layers/` are read-only inputs.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    default_weights = paths.workspace / "config" / "default_weights.json"
    default_weights.parent.mkdir(parents=True, exist_ok=True)
    if not default_weights.exists():
        default_weights.write_text(
            json.dumps(
                {
                    "direct_source_genre": {"weight": 80, "confidence": 0.9},
                    "legacy_unclassified_tag": {"weight": 50, "confidence": 0.6},
                    "explicit_contributor_relation": {"weight": 50, "confidence": 0.8},
                    "heuristic_relation": {"weight": 25, "confidence": 0.4},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return paths


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def generate_inventory(project_root: Path, source_root: Path) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    summary_counts = read_summary_counts(source_root / "layers" / "summary.tsv")
    files = []
    for name in LOCAL_INPUTS:
        path = source_root / "layers" / name
        files.append(inspect_input_file(path, summary_counts))
    report = {
        "generatedAt": utc_now(),
        "sourceRoot": str(source_root),
        "files": files,
    }
    write_json(paths.reports / "inventory.json", report)
    return report


def read_summary_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.is_file():
        return counts
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            key = row.get("metric")
            value = row.get("value")
            if key and value and value.isdigit():
                counts[key] = int(value)
    return counts


def inspect_input_file(path: Path, summary_counts: dict[str, int]) -> dict[str, Any]:
    exists = path.is_file()
    suffixes = path.name.split(".")
    compression = "zst" if path.name.endswith(".zst") else None
    fmt = detect_format(path.name)
    entry: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "size": path.stat().st_size if exists else None,
        "format": fmt,
        "compression": compression,
        "detectedColumns": [],
        "detectedJsonKeys": [],
        "estimatedRows": None,
        "role": input_role(path.name),
        "indexRequired": path.suffix == ".jsonl" and path.stat().st_size > 50_000_000 if exists else False,
        "used": False,
    }
    if not exists:
        return entry
    if path.name.endswith(".jsonl") or path.name.endswith(".jsonl.zst"):
        sample = first_json_rows(path, limit=2)
        if sample:
            keys: set[str] = set()
            claim_keys: set[str] = set()
            for row in sample:
                keys.update(row)
                claims = row.get("claims")
                if isinstance(claims, dict):
                    claim_keys.update(claims)
            entry["detectedJsonKeys"] = sorted(keys)
            entry["detectedClaimKeysSample"] = sorted(claim_keys)[:50]
        layer_name = path.name.removesuffix(".jsonl").removesuffix(".zst")
        entry["estimatedRows"] = summary_counts.get(f"layer_{layer_name}")
    elif path.suffix == ".tsv":
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            first = next(reader, [])
            entry["detectedColumns"] = first
        if path.stat().st_size < 20_000_000:
            entry["estimatedRows"] = max(0, sum(1 for _ in path.open(encoding="utf-8", errors="replace")) - 1)
    elif path.suffix == ".txt":
        if path.stat().st_size < 20_000_000:
            entry["estimatedRows"] = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    elif path.suffix == ".sqlite":
        entry["sqliteSchema"] = sqlite_schema(path)
    return entry


def detect_format(name: str) -> str:
    if name.endswith(".jsonl.zst"):
        return "jsonl"
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".tsv"):
        return "tsv"
    if name.endswith(".sqlite"):
        return "sqlite"
    if name.endswith(".txt"):
        return "text"
    return "unknown"


def input_role(name: str) -> str:
    if name == "summary.tsv":
        return "local data inventory summary"
    if name == "taxonomy.sqlite":
        return "work and concept taxonomy"
    if name == "used_ids.sqlite":
        return "used QID/PID lookup"
    if name == "work_class_map.tsv":
        return "work type classification"
    if name.startswith("people_"):
        return "selected people claims or occupation mapping"
    if name.endswith(".jsonl") or name.endswith(".jsonl.zst"):
        return "Wikidata-derived layer records"
    return "supporting input"


def first_json_rows(path: Path, *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if path.name.endswith(".zst"):
        zstd = shutil.which("zstd")
        if zstd is None:
            return rows
        proc = subprocess.Popen(
            [zstd, "-dc", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                parsed = parse_json_line(line)
                if parsed is not None:
                    rows.append(parsed)
                    if len(rows) >= limit:
                        break
        finally:
            proc.kill()
            proc.wait()
        return rows
    with path.open("rb") as handle:
        for raw in handle:
            parsed = parse_json_line(raw)
            if parsed is not None:
                rows.append(parsed)
                if len(rows) >= limit:
                    break
    return rows


def parse_json_line(raw: bytes | str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def sqlite_schema(path: Path) -> list[dict[str, Any]]:
    db = sqlite3.connect(path)
    try:
        return [
            {"name": row[0], "type": row[1], "sql": row[2]}
            for row in db.execute(
                """
                select name, type, sql
                from sqlite_master
                where type in ('table', 'index', 'view')
                order by type, name
                """
            )
        ]
    finally:
        db.close()


def generate_current_database_report(project_root: Path, db_path: Path) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        tables = [
            row["name"]
            for row in db.execute(
                "select name from sqlite_master where type='table' order by name"
            )
        ]
        report = {
            "generatedAt": utc_now(),
            "path": str(db_path),
            "size": db_path.stat().st_size,
            "sha256": sha256_file(db_path),
            "integrityCheck": db.execute("pragma integrity_check").fetchone()[0],
            "foreignKeyCheck": [list(row) for row in db.execute("pragma foreign_key_check")],
            "tables": {},
            "indexes": sqlite_master_rows(db, "index"),
            "views": sqlite_master_rows(db, "view"),
            "entityKindDistribution": rows_as_dicts(
                db.execute(
                    """
                    select entity_kind, count(*) as count
                    from entities
                    group by entity_kind
                    order by entity_kind
                    """
                )
            ),
            "tagNamespaceDistribution": rows_as_dicts(
                db.execute(
                    """
                    select coalesce(namespace, '') as namespace, count(*) as count
                    from tags
                    group by namespace
                    order by namespace
                    """
                )
            ),
            "datePrecisionDistribution": rows_as_dicts(
                db.execute(
                    """
                    select date_precision, count(*) as count
                    from entities
                    group by date_precision
                    order by date_precision
                    """
                )
            ),
            "externalReferenceCoverage": rows_as_dicts(
                db.execute(
                    """
                    select ref_kind, count(*) as count, count(distinct entity_id) as entities
                    from entity_refs
                    group by ref_kind
                    order by ref_kind
                    """
                )
            ),
            "genericAssociatedRelations": db.execute(
                "select count(*) from entity_links where link_kind = 0"
            ).fetchone()[0],
        }
        for table in tables:
            report["tables"][table] = {
                "rowCount": db.execute(f'select count(*) from "{table}"').fetchone()[0],
                "columns": rows_as_dicts(db.execute(f'pragma table_info("{table}")')),
                "foreignKeys": rows_as_dicts(db.execute(f'pragma foreign_key_list("{table}")')),
            }
    finally:
        db.close()
    write_json(paths.reports / "current_database.json", report)
    return report


def sqlite_master_rows(db: sqlite3.Connection, kind: str) -> list[dict[str, Any]]:
    return rows_as_dicts(
        db.execute(
            """
            select name, tbl_name, sql
            from sqlite_master
            where type = ?
            order by name
            """,
            (kind,),
        )
    )


def rows_as_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def build_layer_index(
    project_root: Path,
    source_root: Path,
    *,
    layers: list[str] | None = None,
    include_other: bool = False,
    qids: set[str] | None = None,
    limit: int | None = None,
    resume: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    index_path = paths.cache / "layer_index.sqlite"
    selected = layers or list(DEFAULT_ART_LAYER_NAMES)
    if include_other and "other_creative_work" not in selected:
        selected.append("other_creative_work")
    db = sqlite3.connect(index_path)
    db.row_factory = sqlite3.Row
    ensure_layer_index_schema(db)
    filter_hash = qid_filter_hash(qids)
    total_records = 0
    total_scanned = 0
    files: list[dict[str, Any]] = []
    for layer in selected:
        path = source_root / "layers" / f"{layer}.jsonl"
        if not path.is_file():
            files.append({"layer": layer, "path": str(path), "indexed": 0, "missing": True})
            continue
        file_stats = index_one_layer_file(
            db,
            layer=layer,
            path=path,
            qids=qids,
            filter_hash=filter_hash,
            limit=None if limit is None else max(0, limit - total_records),
            resume=resume,
            verbose=verbose,
        )
        indexed = int(file_stats["indexed"])
        total_records += indexed
        total_scanned += int(file_stats["scanned"])
        files.append({"layer": layer, "path": str(path), "missing": False, **file_stats})
        if limit is not None and total_records >= limit:
            break
    db.commit()
    db.close()
    return {
        "index": str(index_path),
        "records": total_records,
        "scanned": total_scanned,
        "qidFilterHash": filter_hash,
        "files": files,
    }


def qid_filter_hash(qids: set[str] | None) -> str:
    if qids is None:
        return "*"
    digest = hashlib.sha256()
    for qid in sorted(qids):
        digest.update(qid.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def ensure_layer_index_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        create table if not exists layer_records (
            qid         text not null,
            layer_name  text not null,
            file_path   text not null,
            byte_offset integer not null,
            byte_length integer not null,
            file_size   integer not null,
            file_mtime  integer not null,
            primary key (qid, layer_name)
        );
        create table if not exists layer_index_checkpoints (
            file_path   text primary key,
            byte_offset integer not null,
            file_size   integer not null,
            file_mtime  integer not null,
            complete    integer not null default 0,
            updated_at  text not null
        );
        """
    )
    checkpoint_columns = {
        row["name"]
        for row in db.execute("pragma table_info(layer_index_checkpoints)")
    }
    if "qid_filter_hash" not in checkpoint_columns:
        db.execute("alter table layer_index_checkpoints add column qid_filter_hash text")
    if "scanned_rows" not in checkpoint_columns:
        db.execute("alter table layer_index_checkpoints add column scanned_rows integer not null default 0")


def index_one_layer_file(
    db: sqlite3.Connection,
    *,
    layer: str,
    path: Path,
    qids: set[str] | None,
    filter_hash: str,
    limit: int | None,
    resume: bool,
    verbose: bool,
) -> dict[str, Any]:
    stat = path.stat()
    file_size = stat.st_size
    file_mtime = int(stat.st_mtime)
    db.execute(
        """
        delete from layer_records
        where file_path = ? and (file_size <> ? or file_mtime <> ?)
        """,
        (str(path), file_size, file_mtime),
    )
    offset = 0
    if resume:
        row = db.execute(
            """
            select byte_offset, file_size, file_mtime, complete, qid_filter_hash, scanned_rows
            from layer_index_checkpoints
            where file_path = ?
            """,
            (str(path),),
        ).fetchone()
        if (
            row
            and row["file_size"] == file_size
            and row["file_mtime"] == file_mtime
            and (row["qid_filter_hash"] or "") == filter_hash
        ):
            if row["complete"]:
                return {
                    "indexed": 0,
                    "scanned": 0,
                    "offset": int(row["byte_offset"]),
                    "complete": True,
                }
            offset = int(row["byte_offset"])
    indexed = 0
    scanned = 0
    malformed = 0
    final_offset = offset
    last_checkpoint = offset
    with path.open("rb") as handle:
        if offset:
            handle.seek(offset)
        while True:
            start = handle.tell()
            raw = handle.readline()
            if not raw:
                final_offset = handle.tell()
                break
            scanned += 1
            final_offset = handle.tell()
            row = parse_json_line(raw)
            if row is None:
                malformed += 1
            else:
                qid = row.get("id")
                if isinstance(qid, str) and (qids is None or qid in qids):
                    db.execute(
                        """
                        insert or replace into layer_records(
                            qid, layer_name, file_path, byte_offset, byte_length,
                            file_size, file_mtime
                        )
                        values (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (qid, layer, str(path), start, len(raw), file_size, file_mtime),
                    )
                    indexed += 1
                    if limit is not None and indexed >= limit:
                        break
            if handle.tell() - last_checkpoint >= 256 * 1024 * 1024:
                db.execute(
                    """
                    insert or replace into layer_index_checkpoints(
                        file_path, byte_offset, file_size, file_mtime, complete,
                        updated_at, qid_filter_hash, scanned_rows
                    )
                    values (?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (str(path), handle.tell(), file_size, file_mtime, utc_now(), filter_hash, scanned),
                )
                db.commit()
                last_checkpoint = handle.tell()
                if verbose:
                    print(f"indexed layer={layer} matched={indexed} scanned={scanned} offset={handle.tell()}")
    db.execute(
        """
        insert or replace into layer_index_checkpoints(
            file_path, byte_offset, file_size, file_mtime, complete,
            updated_at, qid_filter_hash, scanned_rows
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(path),
            final_offset,
            file_size,
            file_mtime,
            1 if limit is None else 0,
            utc_now(),
            filter_hash,
            scanned,
        ),
    )
    if malformed:
        db.execute(
            """
            create table if not exists layer_index_errors (
                file_path text not null,
                error_kind text not null,
                count integer not null,
                updated_at text not null,
                primary key (file_path, error_kind)
            )
            """
        )
        db.execute(
            """
            insert or replace into layer_index_errors(file_path, error_kind, count, updated_at)
            values (?, 'malformed_json', ?, ?)
            """,
            (str(path), malformed, utc_now()),
        )
    return {"indexed": indexed, "scanned": scanned, "offset": final_offset, "complete": limit is None}


def build_people_cache(
    project_root: Path,
    source_root: Path,
    db_path: Path,
    *,
    qids: set[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    zst_path = source_root / "layers" / "people_selected_claims.jsonl.zst"
    cache_path = paths.cache / "people_claims.sqlite"
    selected = qids or referenced_secondary_qids(db_path)
    db = sqlite3.connect(cache_path)
    db.execute(
        """
        create table if not exists people_claims (
            qid text primary key,
            payload_json text not null,
            file_path text not null,
            file_size integer not null,
            file_mtime integer not null,
            cached_at text not null
        )
        """
    )
    if not zst_path.is_file():
        db.close()
        return {"cache": str(cache_path), "records": 0, "missing": str(zst_path)}
    zstd = shutil.which("zstd")
    if zstd is None:
        db.close()
        return {"cache": str(cache_path), "records": 0, "error": "zstd executable not found"}
    stat = zst_path.stat()
    proc = subprocess.Popen(
        [zstd, "-dc", str(zst_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    records = 0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            row = parse_json_line(line)
            if row is None:
                continue
            qid = row.get("id")
            if not isinstance(qid, str) or qid not in selected:
                continue
            db.execute(
                """
                insert or replace into people_claims(
                    qid, payload_json, file_path, file_size, file_mtime, cached_at
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (qid, json.dumps(row, separators=(",", ":")), str(zst_path), stat.st_size, int(stat.st_mtime), utc_now()),
            )
            records += 1
            if limit is not None and records >= limit:
                break
            if records % 1000 == 0:
                db.commit()
    finally:
        proc.kill()
        proc.wait()
        db.commit()
        db.close()
    return {"cache": str(cache_path), "records": records}


def referenced_secondary_qids(db_path: Path) -> set[str]:
    db = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in db.execute(
                """
                select r.ref_value
                from entity_refs r
                join entities e on e.entity_id = r.entity_id
                where r.ref_kind = ? and e.is_catalogued = 0
                """,
                (REF_KIND_WIKIDATA,),
            )
        }
    finally:
        db.close()


def schema_status(db_path: Path) -> list[dict[str, Any]]:
    db = connect_art(db_path)
    try:
        return [
            {
                "version": item.version,
                "name": item.name,
                "checksum": item.checksum,
                "applied": item.applied,
            }
            for item in migration_status(db)
        ]
    finally:
        db.close()


def migrate_schema(db_path: Path, *, dry_run: bool = False) -> list[dict[str, Any]]:
    db = connect_art(db_path)
    try:
        completed = run_migrations(db, dry_run=dry_run)
        return [
            {
                "version": item.version,
                "name": item.name,
                "checksum": item.checksum,
                "applied": not dry_run,
            }
            for item in completed
        ]
    finally:
        db.close()


def migrate_existing_database(
    project_root: Path,
    source_db: Path,
    target_db: Path,
    *,
    replace: bool = False,
    dry_run: bool = False,
    backup: bool = False,
) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    source_report = generate_current_database_report(project_root, source_db)
    if source_report["integrityCheck"] != "ok" or source_report["foreignKeyCheck"]:
        raise MigrationError("source database failed integrity or foreign-key checks")
    backup_path = backup_database(source_db, project_root / "data") if backup else None
    if dry_run:
        return {
            "dryRun": True,
            "source": str(source_db),
            "target": str(target_db),
            "backup": str(backup_path) if backup_path else None,
        }
    if target_db.exists():
        if not replace:
            raise FileExistsError(f"target database already exists: {target_db}")
        unlink_sqlite_artifacts(target_db)
    copy_sqlite_database(source_db, target_db)
    db = connect_art(target_db)
    try:
        run_migrations(db)
        seed_v2_definitions(db)
        migrate_v1_rows_to_v2(db)
        db.commit()
        write_migration_reports(paths, db)
        validation = validate_v2_database(project_root, source_db, target_db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "source": str(source_db),
        "target": str(target_db),
        "backup": str(backup_path) if backup_path else None,
        "validation": validation,
    }


def backup_database(source_db: Path, data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = data_dir / f"{source_db.stem}.backup-{stamp}.sqlite"
    copy_sqlite_database(source_db, backup_path)
    return backup_path


def unlink_sqlite_artifacts(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()


def copy_sqlite_database(source_db: Path, target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(source_db)
    target = sqlite3.connect(target_db)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def seed_v2_definitions(db: sqlite3.Connection) -> None:
    db.executemany(
        """
        insert or ignore into data_sources(code, label, source_type, base_url)
        values (?, ?, ?, ?)
        """,
        DATA_SOURCES,
    )
    db.executemany(
        """
        insert or ignore into entity_type_definitions(code, family, label, description)
        values (?, ?, ?, ?)
        """,
        ENTITY_TYPE_DEFINITIONS,
    )
    db.executemany(
        """
        insert or ignore into identifier_schemes(
            code, label, entity_family, value_pattern, url_template
        )
        values (?, ?, ?, ?, ?)
        """,
        IDENTIFIER_SCHEMES,
    )
    db.executemany(
        """
        insert or ignore into relation_types(
            code, label, category, source_family, target_family, inverse_code
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        RELATION_TYPES,
    )
    db.executemany(
        """
        insert or ignore into concept_categories(code, label)
        values (?, ?)
        """,
        [(code, code.replace("_", " ").title()) for code in CONCEPT_CATEGORIES],
    )
    db.executemany(
        """
        insert or ignore into advisory_categories(code, label)
        values (?, ?)
        """,
        [(code, code.replace("_", " ").title()) for code in ADVISORY_CATEGORIES],
    )
    db.executemany(
        """
        insert or ignore into measurement_types(code, label, default_unit)
        values (?, ?, ?)
        """,
        MEASUREMENT_TYPES,
    )


def migrate_v1_rows_to_v2(db: sqlite3.Connection) -> None:
    legacy_source_id = ensure_source_record(
        db,
        data_source_code="legacy_database",
        external_id="data/art-islands.sqlite",
        local_path="data/art-islands.sqlite",
    )
    update_entity_v2_cache_fields(db)
    migrate_entity_texts(db, legacy_source_id)
    migrate_entity_types(db, legacy_source_id)
    migrate_identifiers(db, legacy_source_id)
    migrate_dates(db, legacy_source_id)
    migrate_concepts(db, legacy_source_id)
    migrate_relations(db, legacy_source_id)


def ensure_source_record(
    db: sqlite3.Connection,
    *,
    data_source_code: str,
    external_id: str | None = None,
    local_path: str | None = None,
    source_url: str | None = None,
    payload_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    source = db.execute(
        "select data_source_id from data_sources where code = ?",
        (data_source_code,),
    ).fetchone()
    if source is None:
        raise MigrationError(f"unknown data source: {data_source_code}")
    metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
    row = db.execute(
        """
        select source_record_id
        from source_records
        where data_source_id = ?
          and coalesce(external_id, '') = coalesce(?, '')
          and coalesce(local_path, '') = coalesce(?, '')
        """,
        (source[0], external_id, local_path),
    ).fetchone()
    if row:
        if payload_hash is not None or metadata_json is not None:
            db.execute(
                """
                update source_records
                set payload_hash = coalesce(?, payload_hash),
                    metadata_json = coalesce(?, metadata_json)
                where source_record_id = ?
                """,
                (payload_hash, metadata_json, row[0]),
            )
        return int(row[0])
    cursor = db.execute(
        """
        insert into source_records(
            data_source_id, external_id, local_path, source_url,
            retrieved_at, metadata_json
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        (source[0], external_id, local_path, source_url, utc_now(), metadata_json),
    )
    if payload_hash is not None:
        db.execute(
            "update source_records set payload_hash = ? where source_record_id = ?",
            (payload_hash, cursor.lastrowid),
        )
    return int(cursor.lastrowid)


def update_entity_v2_cache_fields(db: sqlite3.Connection) -> None:
    now = utc_now()
    db.execute(
        """
        update entities
        set
            entity_family = case
                when entity_kind in (1, 2, 6, 7) then 'work'
                when entity_kind = 3 then 'person'
                when entity_kind = 4 then 'group'
                when entity_kind = 5 then 'organization'
                when entity_kind = 8 then 'concept'
                else 'unknown'
            end,
            completeness_status = case
                when label glob 'Q[0-9]*' or release_date is null or entity_kind = 0 then 'incomplete'
                else 'partial'
            end,
            confidence = 1.0,
            review_state = 'unreviewed',
            created_at = coalesce(created_at, ?),
            updated_at = ?
        """,
        (now, now),
    )


def migrate_entity_texts(db: sqlite3.Connection, source_record_id: int) -> None:
    db.execute("delete from entity_texts")
    db.execute(
        """
        insert into entity_texts(entity_id, text_kind, language, value, is_primary, source_record_id)
        select entity_id, 'label', null, label, 1, ?
        from entities
        where label is not null and label <> ''
        """,
        (source_record_id,),
    )


def migrate_entity_types(db: sqlite3.Connection, source_record_id: int) -> None:
    db.execute("delete from entity_types")
    kind_to_code = {
        0: "unknown",
        1: "film",
        2: "music_album",
        3: "person",
        4: "creative_group",
        5: "organization",
        6: "video_game",
        7: "other_creative_work",
        8: "genre",
    }
    rows = []
    type_ids = definition_ids(db, "entity_type_definitions", "entity_type_id")
    for row in db.execute("select entity_id, entity_kind from entities order by entity_id"):
        code = kind_to_code.get(int(row["entity_kind"]), "unknown")
        rows.append((row["entity_id"], type_ids[code], 1, 1.0, source_record_id))
    db.executemany(
        """
        insert or ignore into entity_types(
            entity_id, entity_type_id, is_primary, confidence, source_record_id
        )
        values (?, ?, ?, ?, ?)
        """,
        rows,
    )


def definition_ids(db: sqlite3.Connection, table: str, id_column: str) -> dict[str, int]:
    return {
        row["code"]: int(row[id_column])
        for row in db.execute(f"select {id_column}, code from {table}")
    }


def migrate_identifiers(db: sqlite3.Connection, source_record_id: int) -> None:
    db.execute("delete from entity_identifiers")
    scheme_ids = definition_ids(db, "identifier_schemes", "identifier_scheme_id")
    ref_kind_to_scheme = {
        REF_KIND_WIKIDATA: "wikidata",
        REF_KIND_IMDB: "imdb_title",
        REF_KIND_TMDB: "tmdb_movie",
        REF_KIND_MUSICBRAINZ: "musicbrainz_release_group",
        REF_KIND_DISCOGS: "discogs_release",
    }
    rows = []
    for row in db.execute(
        """
        select entity_id, ref_kind, ref_value
        from entity_refs
        order by entity_id, ref_kind, ref_value
        """
    ):
        code = ref_kind_to_scheme.get(int(row["ref_kind"]))
        if code is None:
            continue
        rows.append((row["entity_id"], scheme_ids[code], row["ref_value"], 1, source_record_id))
    db.executemany(
        """
        insert or ignore into entity_identifiers(
            entity_id, identifier_scheme_id, value, is_primary, source_record_id
        )
        values (?, ?, ?, ?, ?)
        """,
        rows,
    )


def migrate_dates(db: sqlite3.Connection, source_record_id: int) -> None:
    db.execute("delete from entity_dates")
    db.execute(
        """
        insert into entity_dates(
            entity_id, date_type, date_value, date_precision,
            rank, is_primary, confidence, source_record_id
        )
        select
            entity_id,
            case
                when entity_kind = 6 then 'release'
                when entity_kind = 2 then 'release'
                when entity_kind in (1, 7) then 'publication'
                else 'point_in_time'
            end,
            release_date,
            date_precision,
            'compatibility',
            1,
            1.0,
            ?
        from entities
        where release_date is not null and date_precision > 0
        """,
        (source_record_id,),
    )


def migrate_concepts(db: sqlite3.Connection, source_record_id: int) -> None:
    db.execute("delete from entity_concepts")
    db.execute("delete from concepts")
    category_ids = definition_ids(db, "concept_categories", "concept_category_id")
    concepts = []
    classification_rows = []
    for tag in db.execute(
        """
        select tag_id, name, description, namespace, value, tag_kind
        from tags
        order by tag_id
        """
    ):
        category, rule, confidence, review = classify_tag(tag)
        concepts.append(
            (
                tag["tag_id"],
                tag["name"],
                tag["description"],
                category_ids[category],
                tag["namespace"],
                tag["value"],
                tag["tag_id"],
                rule,
                confidence,
                1 if review else 0,
            )
        )
        classification_rows.append((tag["tag_id"], tag["name"], category, rule, confidence, int(review)))
    db.executemany(
        """
        insert into concepts(
            concept_id, label, description, concept_category_id,
            namespace, value, legacy_tag_id, classification_rule,
            confidence, review_recommended
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        concepts,
    )
    db.execute(
        """
        insert into entity_concepts(
            entity_id, concept_id, weight, polarity, confidence, is_manual, source_record_id
        )
        select entity_id, tag_id, weight, polarity, 1.0, 0, ?
        from entity_tags
        """,
        (source_record_id,),
    )


def classify_tag(tag: sqlite3.Row) -> tuple[str, str, float, bool]:
    namespace = tag["namespace"] or ""
    name = tag["name"] or ""
    if namespace in CONCEPT_CATEGORIES:
        return namespace, f"namespace:{namespace}", 0.9, False
    namespace_map = {
        "genre": "genre",
        "theme": "theme",
        "subject": "subject",
        "style": "style",
        "movement": "movement",
        "mood": "mood",
        "motif": "motif",
        "setting": "setting",
        "trope": "trope",
        "audience": "audience",
        "format": "format",
        "technique": "technique",
        "language": "language",
        "country": "country",
        "period": "period",
        "franchise": "franchise",
        "adaptation": "subject",
    }
    if namespace in namespace_map:
        return namespace_map[namespace], f"namespace:{namespace}", 0.85, False
    prefix_map = {
        "genre_": "genre",
        "theme_": "theme",
        "subject_": "subject",
        "style_": "style",
        "mood_": "mood",
        "setting_": "setting",
        "motif_": "motif",
        "trope_": "trope",
        "format_": "format",
    }
    for prefix, category in prefix_map.items():
        if name.startswith(prefix):
            return category, f"label_prefix:{prefix}", 0.65, True
    lowered = name.replace("-", "_").lower()
    if any(token in lowered for token in ("horror", "noir", "comedy", "thriller", "drama", "western")):
        return "genre", "label_contains:genre_keyword", 0.6, True
    if any(
        token in lowered
        for token in ("rock", "punk", "metal", "jazz", "ambient", "drone", "folk", "electronic")
    ):
        return "style", "label_contains:music_style_keyword", 0.6, True
    if any(token in lowered for token in ("dream", "memory", "identity", "alienation", "grief", "revenge")):
        return "theme", "label_contains:theme_keyword", 0.55, True
    if any(token in lowered for token in ("urban", "rural", "space", "underwater", "desert", "forest")):
        return "setting", "label_contains:setting_keyword", 0.55, True
    if "__" in name and (
        name.startswith("influence_")
        or name.startswith("influenced_")
        or name.startswith("adapted_from_")
    ):
        return "other", "legacy_relation_text", 0.5, True
    return "other", "fallback:other", 0.5, True


def migrate_relations(db: sqlite3.Connection, source_record_id: int) -> None:
    db.execute("delete from entity_relations")
    relation_ids = definition_ids(db, "relation_types", "relation_type_id")
    rows = []
    for link in db.execute(
        """
        select l.source_entity_id, l.target_entity_id, l.link_kind, l.weight,
               l.polarity, l.legacy_tag_id, t.name as legacy_tag_name
        from entity_links l
        left join tags t on t.tag_id = l.legacy_tag_id
        order by l.source_entity_id, l.target_entity_id, l.link_kind
        """
    ):
        code = relation_code_from_link(link)
        rows.append(
            (
                link["source_entity_id"],
                link["target_entity_id"],
                relation_ids[code],
                None,
                None,
                link["weight"],
                1.0 if link["legacy_tag_id"] else 0.8,
                link["polarity"],
                1 if link["legacy_tag_id"] else 0,
                source_record_id,
            )
        )
    db.executemany(
        """
        insert or ignore into entity_relations(
            source_entity_id, target_entity_id, relation_type_id,
            role_label, character_label, weight, confidence, polarity,
            is_manual, source_record_id
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def relation_code_from_link(link: sqlite3.Row) -> str:
    legacy = link["legacy_tag_name"] or ""
    if legacy.startswith("adapted_from_") or int(link["link_kind"]) == 3:
        return "adapted_from"
    if legacy.startswith("influence_") or int(link["link_kind"]) == 1:
        return "influenced_by"
    if legacy.startswith("influenced_") or int(link["link_kind"]) == 2:
        return "influenced"
    return "associated"


def write_migration_reports(paths: MigrationPaths, db: sqlite3.Connection) -> None:
    write_tsv(
        paths.reports / "entity_type_distribution.tsv",
        ("entity_type", "family", "count"),
        db.execute(
            """
            select d.code, d.family, count(*) as count
            from entity_types t
            join entity_type_definitions d on d.entity_type_id = t.entity_type_id
            group by d.code, d.family
            order by count desc, d.code
            """
        ),
    )
    write_tsv(
        paths.reports / "relation_type_distribution.tsv",
        ("relation_type", "category", "count"),
        db.execute(
            """
            select t.code, t.category, count(r.entity_relation_id) as count
            from relation_types t
            left join entity_relations r on r.relation_type_id = t.relation_type_id
            group by t.code, t.category
            order by count desc, t.code
            """
        ),
    )
    write_tsv(
        paths.reports / "concept_classification.tsv",
        ("tag_id", "tag_name", "category", "rule", "confidence", "review_recommended"),
        db.execute(
            """
            select c.legacy_tag_id, c.label as concept_label, cc.code, c.classification_rule,
                   c.confidence, c.review_recommended
            from concepts c
            join concept_categories cc on cc.concept_category_id = c.concept_category_id
            order by c.legacy_tag_id
            """
        ),
    )
    write_tsv(
        paths.reports / "unclassified_tags.tsv",
        ("tag_id", "tag_name", "rule", "review_recommended"),
        db.execute(
            """
            select c.legacy_tag_id, c.label, c.classification_rule, c.review_recommended
            from concepts c
            join concept_categories cc on cc.concept_category_id = c.concept_category_id
            where cc.code = 'other'
            order by c.legacy_tag_id
            """
        ),
    )
    write_tsv(
        paths.reports / "date_precision_before_after.tsv",
        ("entity_id", "label", "old_date", "old_precision", "new_date_type", "new_date", "new_precision"),
        db.execute(
            """
            select e.entity_id, e.label, e.release_date, e.date_precision,
                   d.date_type, d.date_value, d.date_precision
            from entities e
            left join entity_dates d on d.entity_id = e.entity_id and d.is_primary = 1
            where e.release_date is not null
            order by e.entity_id
            """
        ),
    )
    write_tsv(
        paths.reports / "external_identifier_coverage.tsv",
        ("scheme", "count", "entities"),
        db.execute(
            """
            select s.code, count(i.entity_identifier_id) as count,
                   count(distinct i.entity_id) as entities
            from identifier_schemes s
            left join entity_identifiers i on i.identifier_scheme_id = s.identifier_scheme_id
            group by s.code
            order by s.code
            """
        ),
    )
    write_tsv(
        paths.reports / "unresolved_entities.tsv",
        ("entity_id", "label", "entity_family", "reason"),
        db.execute(
            """
            select entity_id, label, entity_family,
                   trim(
                     case when label glob 'Q[0-9]*' then 'raw_qid_label ' else '' end ||
                     case when entity_family = 'unknown' then 'unknown_family ' else '' end ||
                     case when is_catalogued = 1 and release_date is null then 'missing_catalog_date ' else '' end
                   ) as reason
            from entities
            where reason <> ''
            order by entity_id
            """
        ),
    )
    write_tsv(paths.reports / "conflicts.tsv", ("source", "entity_id", "field", "existing", "candidate", "resolution"), [])
    write_json(paths.reports / "remote_requests.json", [])


def write_tsv(path: Path, header: tuple[str, ...], rows: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            if isinstance(row, sqlite3.Row):
                writer.writerow([row[index] for index in range(len(row))])
            else:
                writer.writerow(list(row))


def export_v2_static_data(
    db_path: Path,
    output_dir: Path,
    settings_path: Path | None = None,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        catalog_ids = {
            int(row["entity_id"])
            for row in db.execute("select entity_id from entities where is_catalogued = 1")
        }
        exported_entity_ids = referenced_export_entity_ids(db, catalog_ids)
        entities = export_v2_entities(db, exported_entity_ids)
        catalog = export_v2_catalog(db, catalog_ids)
        entity_types = {
            "definitions": rows_as_dicts(
                db.execute(
                    """
                    select entity_type_id as id, code, family, label, description
                    from entity_type_definitions
                    order by code
                    """
                )
            ),
            "assignments": rows_as_dicts(
                db.execute(
                    """
                    select entity_id as entityId, entity_type_id as typeId,
                           is_primary as isPrimary, confidence
                    from entity_types
                    where entity_id in (%s)
                    order by entity_id, entity_type_id
                    """
                    % placeholders(exported_entity_ids),
                    tuple(exported_entity_ids),
                )
            )
            if exported_entity_ids
            else [],
        }
        relations = export_v2_relations(db, catalog_ids, exported_entity_ids)
        concepts = export_v2_concepts(db, catalog_ids)
        advisories = rows_as_dicts(
            db.execute(
                """
                select entity_advisory_id as id, entity_id as entityId,
                       advisory_category_id as categoryId, concept_id as conceptId,
                       severity, confidence, description
                from entity_advisories
                where entity_id in (%s)
                order by entity_id, advisory_category_id
                """
                % placeholders(catalog_ids),
                tuple(catalog_ids),
            )
        ) if catalog_ids else []
        ratings = rows_as_dicts(
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
        ) if catalog_ids else []
        restrictions = rows_as_dicts(
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
        ) if catalog_ids else []
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
                   is_catalogued as catalogued, completeness_status as completenessStatus,
                   confidence, review_state as reviewState
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
    texts = grouped_rows(
        db.execute(
            """
            select entity_id, text_kind, language, value, is_primary
            from entity_texts
            where entity_id in (%s)
            order by entity_id, text_kind, language, value
            """
            % placeholders(entity_ids),
            tuple(entity_ids),
        ),
        "entity_id",
        lambda row: {
            "kind": row["text_kind"],
            "language": row["language"],
            "value": row["value"],
            "primary": bool(row["is_primary"]),
        },
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
        if texts.get(row["id"]):
            entity["texts"] = texts[row["id"]]
        result[str(row["id"])] = entity
    return result


def grouped_rows(rows: Iterable[sqlite3.Row], key: str, transform) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = {}
    for row in rows:
        grouped.setdefault(int(row[key]), []).append(transform(row))
    return grouped


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
                "manual": bool(row["is_manual"]),
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
    entity_concepts = rows_as_dicts(
        db.execute(
            """
            select ec.entity_id as entityId, ec.concept_id as conceptId,
                   ec.weight, ec.polarity, ec.confidence, ec.is_manual as manual
            from entity_concepts ec
            where ec.entity_id in (%s)
            order by ec.entity_id, ec.weight desc, ec.concept_id
            """
            % placeholders(catalog_ids),
            tuple(catalog_ids),
        )
    ) if catalog_ids else []
    return {
        "categories": categories,
        "concepts": [compact_dict(row) for row in concept_rows],
        "entityConcepts": entity_concepts,
    }


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def validate_v2_database(project_root: Path, source_db: Path, v2_db: Path) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    source = sqlite3.connect(source_db)
    target = sqlite3.connect(v2_db)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
    try:
        source_catalog_qids = catalog_qids(source, source_table="entity_refs")
        target_catalog_qids = catalog_qids_v2(target)
        tag_mismatches = target.execute(
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
        source_identifier_pairs = source_ref_identifier_pairs(source)
        target_identifier_pairs = v2_identifier_pairs(target)
        missing_source_identifiers = sorted(source_identifier_pairs - target_identifier_pairs)
        ref_count = len(source_identifier_pairs)
        identifier_count = target.execute("select count(*) from entity_identifiers").fetchone()[0]
        summary = {
            "generatedAt": utc_now(),
            "source": str(source_db),
            "v2": str(v2_db),
            "sourceIntegrity": source.execute("pragma integrity_check").fetchone()[0],
            "v2Integrity": target.execute("pragma integrity_check").fetchone()[0],
            "sourceForeignKeys": [list(row) for row in source.execute("pragma foreign_key_check")],
            "v2ForeignKeys": [list(row) for row in target.execute("pragma foreign_key_check")],
            "catalogQids": {
                "source": len(source_catalog_qids),
                "v2": len(target_catalog_qids),
                "missingInV2": sorted(source_catalog_qids - target_catalog_qids)[:100],
                "extraInV2": sorted(target_catalog_qids - source_catalog_qids)[:100],
            },
            "manualTagWeightPolarityMismatches": int(tag_mismatches),
            "externalIdentifiers": {
                "sourceRefs": int(ref_count),
                "v2Identifiers": int(identifier_count),
                "sourceRefsPreserved": not missing_source_identifiers,
                "missingSourceRefs": [
                    {"scheme": scheme, "value": value}
                    for scheme, value in missing_source_identifiers[:100]
                ],
            },
            "supportsMultipleIdentifiers": supports_multiple_identifiers(target),
            "supportsMultipleRolesPerEntityPair": supports_multiple_roles(target),
            "multipleDatesStored": target.execute("select count(*) from entity_dates").fetchone()[0],
            "unclassifiedTagsRetained": target.execute(
                """
                select count(*)
                from concepts c
                join concept_categories cc on cc.concept_category_id = c.concept_category_id
                where cc.code = 'other'
                """
            ).fetchone()[0],
            "remoteCacheOfflineMode": True,
            "largeJsonlIndexAvailable": (paths.cache / "layer_index.sqlite").exists(),
        }
        summary["ok"] = (
            summary["sourceIntegrity"] == "ok"
            and summary["v2Integrity"] == "ok"
            and not summary["sourceForeignKeys"]
            and not summary["v2ForeignKeys"]
            and not summary["catalogQids"]["missingInV2"]
            and summary["manualTagWeightPolarityMismatches"] == 0
            and summary["externalIdentifiers"]["sourceRefsPreserved"]
            and summary["supportsMultipleIdentifiers"]
            and summary["supportsMultipleRolesPerEntityPair"]
        )
    finally:
        target.close()
        source.close()
    write_json(paths.reports / "validation_summary.json", summary)
    return summary


def catalog_qids(db: sqlite3.Connection, *, source_table: str) -> set[str]:
    return {
        row[0]
        for row in db.execute(
            f"""
            select r.ref_value
            from {source_table} r
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


def supports_multiple_identifiers(db: sqlite3.Connection) -> bool:
    try:
        db.execute("begin")
        entity_id = db.execute("select min(entity_id) from entities").fetchone()[0]
        scheme_id = db.execute(
            "select identifier_scheme_id from identifier_schemes where code = 'wikidata'"
        ).fetchone()[0]
        db.execute(
            """
            insert into entity_identifiers(entity_id, identifier_scheme_id, value)
            values (?, ?, 'Q999999990')
            """,
            (entity_id, scheme_id),
        )
        db.execute(
            """
            insert into entity_identifiers(entity_id, identifier_scheme_id, value)
            values (?, ?, 'Q999999991')
            """,
            (entity_id, scheme_id),
        )
        db.rollback()
        return True
    except sqlite3.IntegrityError:
        db.rollback()
        return False


def supports_multiple_roles(db: sqlite3.Connection) -> bool:
    try:
        db.execute("begin")
        ids = [row[0] for row in db.execute("select entity_id from entities order by entity_id limit 2")]
        if len(ids) < 2:
            db.rollback()
            return False
        director = db.execute("select relation_type_id from relation_types where code = 'director'").fetchone()[0]
        writer = db.execute("select relation_type_id from relation_types where code = 'writer'").fetchone()[0]
        db.execute(
            """
            insert into entity_relations(source_entity_id, target_entity_id, relation_type_id)
            values (?, ?, ?)
            """,
            (ids[0], ids[1], director),
        )
        db.execute(
            """
            insert into entity_relations(source_entity_id, target_entity_id, relation_type_id)
            values (?, ?, ?)
            """,
            (ids[0], ids[1], writer),
        )
        db.rollback()
        return True
    except sqlite3.IntegrityError:
        db.rollback()
        return False


def enrich_local(
    project_root: Path,
    db_path: Path,
    *,
    source_root: Path | None = None,
    qids: set[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    resume: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    source_root = source_root or project_root.parent
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        seed_v2_definitions(db)
        before = enrichment_coverage_counts(db)
        qid_to_entity = wikidata_entity_map(db)
        selected_qids = sorted(qids or set(qid_to_entity))
        if limit is not None:
            selected_qids = selected_qids[:limit]
        selected_qid_set = set(selected_qids)
        if not selected_qid_set:
            return {"updated": 0, "skipped": 0, "unresolved": 0, "failed": 0, "dryRun": dry_run}

        layers = list(DEFAULT_ART_LAYER_NAMES)
        if "other_creative_work" not in layers:
            layers.append("other_creative_work")
        if "people" not in layers:
            layers.append("people")
        index_result = build_layer_index(
            project_root,
            source_root,
            layers=layers,
            qids=selected_qid_set,
            resume=resume,
            verbose=verbose,
        )
        local_records = load_indexed_layer_rows(paths.cache / "layer_index.sqlite", selected_qid_set)
        target_qids = referenced_qids_from_records(local_records)
        text_qids = selected_qid_set | target_qids
        text_lookup = load_id_map_texts(source_root / "layers" / "id_map.slow.partial.jsonl", text_qids)
        people_qids = {
            qid
            for qid in text_qids
            if qid in target_qids or entity_type_hint(qid_to_entity.get(qid), db) == "person"
        }
        people_result = build_people_cache(project_root, source_root, db_path, qids=people_qids) if people_qids else {
            "records": 0
        }
        people_records = load_people_claim_cache(paths.cache / "people_claims.sqlite", people_qids)

        if dry_run:
            missing = db.execute(
                """
                select count(*)
                from entities
                where is_catalogued = 1
                  and (release_date is null or entity_kind = 0 or label glob 'Q[0-9]*')
                """
            ).fetchone()[0]
            return {
                "updated": 0,
                "skipped": 0,
                "unresolved": int(missing),
                "failed": 0,
                "dryRun": True,
                "indexed": index_result,
                "peopleCache": people_result,
            }

        counts = {
            "updated": 0,
            "skipped": 0,
            "unresolved": 0,
            "failed": 0,
            "labels": 0,
            "descriptions": 0,
            "aliases": 0,
            "dates": 0,
            "datePrecisionImprovements": 0,
            "types": 0,
            "images": 0,
            "identifiers": 0,
            "relations": 0,
            "concepts": 0,
            "measurements": 0,
            "manualConceptFlagsCleared": 0,
            "conceptsReclassified": 0,
            "peopleClaimsApplied": 0,
        }
        counts["manualConceptFlagsCleared"] = clear_migrated_concept_manual_flags(db)
        counts["conceptsReclassified"] = reclassify_existing_concepts(db)
        source_records: dict[tuple[str, str, str], int] = {}

        for qid in selected_qids:
            entity_id = qid_to_entity.get(qid)
            if entity_id is None:
                continue
            row_counts = apply_id_map_texts(db, entity_id, text_lookup.get(qid), source_records)
            records = local_records.get(qid, [])
            for local in records:
                apply_counts = apply_local_layer_record(
                    db,
                    entity_id,
                    qid,
                    local,
                    qid_to_entity,
                    text_lookup,
                    source_records,
                )
                merge_counts(counts, apply_counts)
            if qid in people_records:
                apply_counts = apply_people_claim_record(
                    db,
                    entity_id,
                    qid,
                    people_records[qid],
                    text_lookup.get(qid),
                    source_records,
                )
                merge_counts(counts, apply_counts)
                if sum(apply_counts.values()):
                    counts["peopleClaimsApplied"] += 1
            merge_counts(counts, row_counts)
            if records or qid in text_lookup or qid in people_records:
                counts["updated"] += 1
            else:
                counts["skipped"] += 1

        refresh_entity_cache_fields(db)
        db.commit()
        write_migration_reports(paths, db)
        after = enrichment_coverage_counts(db)
        unresolved = db.execute(
            """
            select count(*)
            from entities
            where is_catalogued = 1
              and (release_date is null or entity_kind = 0 or label glob 'Q[0-9]*')
            """
        ).fetchone()[0]
        counts["unresolved"] = int(unresolved)
        report = {
            "generatedAt": utc_now(),
            "database": str(db_path),
            "sourceRoot": str(source_root),
            "before": before,
            "after": after,
            "counts": counts,
            "index": index_result,
            "peopleCache": people_result,
            "sourceUsage": source_usage_counts(db),
            "fieldsNotPopulated": fields_not_populated(db),
        }
        write_json(paths.reports / "enrichment_summary.json", report)
    finally:
        db.close()
    return {
        "updated": int(counts["updated"]),
        "skipped": int(counts["skipped"]),
        "unresolved": int(unresolved),
        "failed": int(counts["failed"]),
        "dryRun": dry_run,
        "labels": int(counts["labels"]),
        "dates": int(counts["dates"]),
        "types": int(counts["types"]),
        "identifiers": int(counts["identifiers"]),
        "relations": int(counts["relations"]),
        "concepts": int(counts["concepts"]),
        "measurements": int(counts["measurements"]),
        "manualConceptFlagsCleared": int(counts["manualConceptFlagsCleared"]),
        "conceptsReclassified": int(counts["conceptsReclassified"]),
        "indexRecords": int(index_result["records"]),
        "indexScanned": int(index_result["scanned"]),
        "peopleClaimsApplied": int(counts["peopleClaimsApplied"]),
    }


def merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = int(target.get(key, 0)) + int(value)


def wikidata_entity_map(db: sqlite3.Connection) -> dict[str, int]:
    return {
        row["value"]: int(row["entity_id"])
        for row in db.execute(
            """
            select i.entity_id, i.value
            from entity_identifiers i
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            where s.code = 'wikidata'
            order by i.entity_id
            """
        )
    }


def entity_type_hint(entity_id: int | None, db: sqlite3.Connection) -> str | None:
    if entity_id is None:
        return None
    row = db.execute(
        """
        select d.code
        from entity_types t
        join entity_type_definitions d on d.entity_type_id = t.entity_type_id
        where t.entity_id = ? and t.is_primary = 1
        order by coalesce(t.confidence, 0) desc, d.code
        limit 1
        """,
        (entity_id,),
    ).fetchone()
    return row["code"] if row else None


def load_indexed_layer_rows(index_path: Path, qids: set[str]) -> dict[str, list[dict[str, Any]]]:
    if not qids or not index_path.is_file():
        return {}
    index = sqlite3.connect(index_path)
    index.row_factory = sqlite3.Row
    entries: list[sqlite3.Row] = []
    try:
        for chunk in batched(sorted(qids), 500):
            entries.extend(
                index.execute(
                    """
                    select qid, layer_name, file_path, byte_offset, byte_length
                    from layer_records
                    where qid in (%s)
                    order by file_path, byte_offset
                    """
                    % placeholders(chunk),
                    tuple(chunk),
                ).fetchall()
            )
    finally:
        index.close()
    by_file: dict[str, list[sqlite3.Row]] = {}
    for entry in entries:
        by_file.setdefault(entry["file_path"], []).append(entry)
    rows: dict[str, list[dict[str, Any]]] = {}
    for file_path, file_entries in sorted(by_file.items()):
        path = Path(file_path)
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            for entry in file_entries:
                handle.seek(int(entry["byte_offset"]))
                raw = handle.read(int(entry["byte_length"]))
                parsed = parse_json_line(raw)
                if parsed is None:
                    continue
                rows.setdefault(entry["qid"], []).append(
                    {
                        "layer": entry["layer_name"],
                        "filePath": file_path,
                        "byteOffset": int(entry["byte_offset"]),
                        "raw": raw,
                        "row": parsed,
                    }
                )
    for qid in rows:
        rows[qid].sort(key=lambda item: WORK_LAYER_ORDER.get(item["layer"], 999))
    return rows


def referenced_qids_from_records(records_by_qid: dict[str, list[dict[str, Any]]]) -> set[str]:
    qids: set[str] = set()
    pids = set(RELATION_PROPERTY_CODES) | set(CONCEPT_PROPERTY_CATEGORIES) | {"P31"}
    for records in records_by_qid.values():
        for record in records:
            claims = local_claims(record)
            for pid in pids:
                qids.update(claim_qids(claims.get(pid)))
    return qids


def load_id_map_texts(path: Path, qids: set[str]) -> dict[str, dict[str, Any]]:
    remaining = set(qids)
    result: dict[str, dict[str, Any]] = {}
    if not remaining or not path.is_file():
        return result
    with path.open("rb") as handle:
        for raw in handle:
            parsed = parse_json_line(raw)
            if parsed is None:
                continue
            qid = parsed.get("id")
            if not isinstance(qid, str) or qid not in remaining:
                continue
            labels = parsed.get("labels") if isinstance(parsed.get("labels"), dict) else {}
            descriptions = parsed.get("descriptions") if isinstance(parsed.get("descriptions"), dict) else {}
            aliases = parsed.get("aliases") if isinstance(parsed.get("aliases"), dict) else {}
            result[qid] = {
                "label": preferred_localized_text(labels),
                "description": preferred_localized_text(descriptions),
                "labels": labels,
                "descriptions": descriptions,
                "aliases": aliases,
            }
            remaining.remove(qid)
            if not remaining:
                break
    return result


def preferred_localized_text(values: dict[str, Any]) -> str | None:
    for language in ("en", "mul", "de", "fr", "es", "ru"):
        value = values.get(language)
        if isinstance(value, str) and value:
            return value
    for key in sorted(values):
        value = values.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def load_people_claim_cache(cache_path: Path, qids: set[str]) -> dict[str, dict[str, Any]]:
    if not qids or not cache_path.is_file():
        return {}
    db = sqlite3.connect(cache_path)
    db.row_factory = sqlite3.Row
    rows: dict[str, dict[str, Any]] = {}
    try:
        for chunk in batched(sorted(qids), 500):
            for row in db.execute(
                """
                select qid, payload_json, file_path
                from people_claims
                where qid in (%s)
                order by qid
                """
                % placeholders(chunk),
                tuple(chunk),
            ):
                parsed = parse_json_line(row["payload_json"])
                if parsed is not None:
                    rows[row["qid"]] = {"row": parsed, "filePath": row["file_path"]}
    finally:
        db.close()
    return rows


def local_claims(record: dict[str, Any]) -> dict[str, Any]:
    row = record.get("row")
    claims = row.get("claims") if isinstance(row, dict) else None
    return claims if isinstance(claims, dict) else {}


def claim_qids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and QID_RE.fullmatch(value)]


def claim_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value]


def first_claim_string(claims: dict[str, Any], pid: str) -> str | None:
    values = claim_strings(claims.get(pid))
    return values[0] if values else None


def claim_texts(values: Any) -> list[tuple[str | None, str]]:
    if not isinstance(values, list):
        return []
    texts = []
    for value in values:
        if isinstance(value, dict):
            text = value.get("text")
            language = value.get("lang") or value.get("language")
            if isinstance(text, str) and text:
                texts.append((language if isinstance(language, str) else None, text))
        elif isinstance(value, str) and value:
            texts.append((None, value))
    return texts


def apply_id_map_texts(
    db: sqlite3.Connection,
    entity_id: int,
    text_info: dict[str, Any] | None,
    source_records: dict[tuple[str, str, str], int],
) -> dict[str, int]:
    counts = {"labels": 0, "descriptions": 0, "aliases": 0}
    if not text_info:
        return counts
    source_record_id = cached_source_record(
        db,
        source_records,
        data_source_code="local_layer",
        external_id=f"id_map:{entity_id}",
        local_path="layers/id_map.slow.partial.jsonl",
        metadata={"kind": "id_map"},
    )
    label = text_info.get("label")
    if isinstance(label, str) and label:
        if update_entity_label_if_missing(db, entity_id, label):
            counts["labels"] += 1
        for language, value in sorted((text_info.get("labels") or {}).items()):
            if insert_text_if_missing(db, entity_id, "label", language, value, value == label, source_record_id):
                counts["labels"] += 1
    description = text_info.get("description")
    if isinstance(description, str) and description:
        if update_entity_description_if_missing(db, entity_id, description):
            counts["descriptions"] += 1
        for language, value in sorted((text_info.get("descriptions") or {}).items()):
            if insert_text_if_missing(db, entity_id, "description", language, value, value == description, source_record_id):
                counts["descriptions"] += 1
    aliases = text_info.get("aliases") or {}
    if isinstance(aliases, dict):
        for language, values in sorted(aliases.items()):
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, str) and insert_text_if_missing(
                    db, entity_id, "alias", language, value, False, source_record_id
                ):
                    counts["aliases"] += 1
    return counts


def apply_local_layer_record(
    db: sqlite3.Connection,
    entity_id: int,
    qid: str,
    record: dict[str, Any],
    qid_to_entity: dict[str, int],
    text_lookup: dict[str, dict[str, Any]],
    source_records: dict[tuple[str, str, str], int],
) -> dict[str, int]:
    counts = {key: 0 for key in ("labels", "descriptions", "dates", "datePrecisionImprovements", "types", "images", "identifiers", "relations", "concepts", "measurements")}
    claims = local_claims(record)
    source_record_id = cached_source_record(
        db,
        source_records,
        data_source_code="local_layer",
        external_id=qid,
        local_path=relative_local_path(record["filePath"]),
        payload_hash=hashlib.sha256(record["raw"]).hexdigest(),
        metadata={"layer": record["layer"], "byteOffset": record["byteOffset"]},
    )
    type_code = type_code_from_local_record(record)
    if type_code and upsert_entity_type(db, entity_id, type_code, True, 0.95, source_record_id):
        counts["types"] += 1
    title_counts = apply_title_claims(db, entity_id, claims, source_record_id)
    merge_counts(counts, title_counts)
    image = first_claim_string(claims, "P18")
    if image and update_entity_image_if_missing(db, entity_id, image):
        counts["images"] += 1
    date_counts = apply_date_claims(db, entity_id, type_code, claims, source_record_id)
    merge_counts(counts, date_counts)
    counts["identifiers"] += apply_identifier_claims(db, entity_id, type_code, qid, claims, source_record_id)
    counts["measurements"] += apply_measurement_claims(db, entity_id, claims, source_record_id)
    counts["concepts"] += apply_concept_claims(db, entity_id, claims, text_lookup, source_record_id)
    counts["relations"] += apply_relation_claims(
        db,
        entity_id,
        type_code,
        claims,
        qid_to_entity,
        text_lookup,
        source_record_id,
    )
    return counts


def apply_people_claim_record(
    db: sqlite3.Connection,
    entity_id: int,
    qid: str,
    record: dict[str, Any],
    text_info: dict[str, Any] | None,
    source_records: dict[tuple[str, str, str], int],
) -> dict[str, int]:
    counts = {key: 0 for key in ("labels", "descriptions", "aliases", "types", "images", "identifiers")}
    source_record_id = cached_source_record(
        db,
        source_records,
        data_source_code="local_people_claims",
        external_id=qid,
        local_path=relative_local_path(record.get("filePath", "layers/people_selected_claims.jsonl.zst")),
    )
    merge_counts(counts, apply_id_map_texts(db, entity_id, text_info, source_records))
    row = record.get("row") if isinstance(record.get("row"), dict) else {}
    claims = row.get("claims") if isinstance(row.get("claims"), dict) else {}
    if "Q5" in claim_qids(claims.get("P31")):
        if upsert_entity_type(db, entity_id, "person", True, 0.95, source_record_id):
            counts["types"] += 1
    image = first_claim_string(claims, "P18")
    if image and update_entity_image_if_missing(db, entity_id, image):
        counts["images"] += 1
    counts["identifiers"] += apply_identifier_claims(db, entity_id, "person", qid, claims, source_record_id)
    return counts


def type_code_from_local_record(record: dict[str, Any]) -> str | None:
    row = record.get("row")
    layers = row.get("layers") if isinstance(row, dict) else None
    layer_names = [record.get("layer")]
    if isinstance(layers, list):
        layer_names.extend(value for value in layers if isinstance(value, str))
    for layer in sorted(set(layer_names), key=lambda item: WORK_LAYER_ORDER.get(item or "", 999)):
        code = LAYER_TYPE_CODES.get(layer or "")
        if code:
            return code
    return None


def relation_code_for_property(pid: str, source_type_code: str | None) -> str | None:
    code = RELATION_PROPERTY_CODES.get(pid)
    if pid == "P170":
        if source_type_code == "painting":
            return "painter"
        if source_type_code == "sculpture":
            return "sculptor"
        if source_type_code == "photograph":
            return "photographer"
    if pid == "P175" and source_type_code in {"music_album", "musical_work"}:
        return "music_artist"
    return code


def semantic_date_type(pid: str, source_type_code: str | None) -> str | None:
    if pid == "P577":
        if source_type_code in {"book", "comics", "musical_work", "other_creative_work"}:
            return "publication"
        if source_type_code == "television_series":
            return "broadcast_start"
        return "release"
    if pid == "P571":
        if source_type_code in {"painting", "sculpture", "photograph", "musical_work"}:
            return "creation"
        return "inception"
    if pid == "P580" and source_type_code == "television_series":
        return "broadcast_start"
    if pid == "P582" and source_type_code == "television_series":
        return "broadcast_end"
    return DATE_PROPERTY_TYPES.get(pid)


def apply_date_claims(
    db: sqlite3.Connection,
    entity_id: int,
    source_type_code: str | None,
    claims: dict[str, Any],
    source_record_id: int,
) -> dict[str, int]:
    counts = {"dates": 0, "datePrecisionImprovements": 0}
    inserted: list[tuple[int, str, int, str]] = []
    for pid in sorted(DATE_PROPERTY_TYPES):
        date_type = semantic_date_type(pid, source_type_code)
        if date_type is None:
            continue
        values = claims.get(pid)
        if not isinstance(values, list):
            continue
        for value in values:
            parsed = parse_wikidata_date(value)
            if parsed is None:
                continue
            date_value, precision = parsed
            date_id = insert_date_if_missing(
                db,
                entity_id,
                date_type,
                date_value,
                precision,
                "wikidata",
                0.95,
                source_record_id,
            )
            if date_id is not None:
                counts["dates"] += 1
            existing = find_entity_date(db, entity_id, date_type, date_value, precision)
            if existing is not None:
                inserted.append((existing, date_value, precision, date_type))
    best = choose_primary_date(source_type_code, inserted)
    if best is not None and update_compatibility_date_if_better(db, entity_id, best[1], best[2]):
        counts["datePrecisionImprovements"] += 1
    if best is not None:
        db.execute("update entity_dates set is_primary = 0 where entity_id = ?", (entity_id,))
        db.execute("update entity_dates set is_primary = 1 where entity_date_id = ?", (best[0],))
    return counts


def choose_primary_date(
    source_type_code: str | None,
    candidates: list[tuple[int, str, int, str]],
) -> tuple[int, str, int, str] | None:
    if not candidates:
        return None
    priority = PRIMARY_DATE_PRIORITY.get(source_type_code or "", ("release", "publication", "creation", "inception", "point_in_time"))
    priority_index = {code: index for index, code in enumerate(priority)}
    return min(
        candidates,
        key=lambda item: (
            priority_index.get(item[3], 999),
            item[1],
            -item[2],
        ),
    )


def insert_date_if_missing(
    db: sqlite3.Connection,
    entity_id: int,
    date_type: str,
    date_value: str,
    precision: int,
    rank: str,
    confidence: float,
    source_record_id: int,
) -> int | None:
    existing = find_entity_date(db, entity_id, date_type, date_value, precision)
    if existing is not None:
        return None
    cursor = db.execute(
        """
        insert into entity_dates(
            entity_id, date_type, date_value, date_precision,
            rank, is_primary, confidence, source_record_id
        )
        values (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (entity_id, date_type, date_value, precision, rank, confidence, source_record_id),
    )
    return int(cursor.lastrowid)


def find_entity_date(db: sqlite3.Connection, entity_id: int, date_type: str, date_value: str, precision: int) -> int | None:
    row = db.execute(
        """
        select entity_date_id
        from entity_dates
        where entity_id = ?
          and date_type = ?
          and date_value = ?
          and date_precision = ?
        limit 1
        """,
        (entity_id, date_type, date_value, precision),
    ).fetchone()
    return int(row["entity_date_id"]) if row else None


def update_compatibility_date_if_better(db: sqlite3.Connection, entity_id: int, date_value: str, precision: int) -> bool:
    row = db.execute(
        "select release_date, date_precision from entities where entity_id = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        return False
    existing_precision = int(row["date_precision"] or 0)
    if row["release_date"] and existing_precision >= precision:
        return False
    db.execute(
        """
        update entities
        set release_date = ?, date_precision = ?, updated_at = ?
        where entity_id = ?
        """,
        (date_value, precision, utc_now(), entity_id),
    )
    return True


def apply_title_claims(db: sqlite3.Connection, entity_id: int, claims: dict[str, Any], source_record_id: int) -> dict[str, int]:
    counts = {"labels": 0}
    for pid in ("P1476", "P1448", "P1705"):
        for language, value in claim_texts(claims.get(pid)):
            if insert_text_if_missing(db, entity_id, "label", language, value, False, source_record_id):
                counts["labels"] += 1
            if update_entity_label_if_missing(db, entity_id, value):
                counts["labels"] += 1
    return counts


def apply_identifier_claims(
    db: sqlite3.Connection,
    entity_id: int,
    source_type_code: str | None,
    qid: str,
    claims: dict[str, Any],
    source_record_id: int,
) -> int:
    count = 0
    count += insert_identifier_if_missing(db, entity_id, "wikidata", qid, True, source_record_id)
    for value in claim_strings(claims.get("P345")):
        if value.startswith("tt"):
            scheme = "imdb_title"
        elif value.startswith("nm"):
            scheme = "imdb_name"
        elif value.startswith("co"):
            scheme = "imdb_company"
        else:
            continue
        count += insert_identifier_if_missing(db, entity_id, scheme, value, False, source_record_id)
    for pid, schemes in IDENTIFIER_PROPERTY_SCHEMES.items():
        scheme = schemes[0]
        for value in claim_strings(claims.get(pid)):
            count += insert_identifier_if_missing(db, entity_id, scheme, value, False, source_record_id)
    return count


def insert_identifier_if_missing(
    db: sqlite3.Connection,
    entity_id: int,
    scheme_code: str,
    value: str,
    is_primary: bool,
    source_record_id: int,
) -> int:
    row = db.execute(
        "select identifier_scheme_id from identifier_schemes where code = ?",
        (scheme_code,),
    ).fetchone()
    if row is None or not value:
        return 0
    before = db.total_changes
    db.execute(
        """
        insert or ignore into entity_identifiers(
            entity_id, identifier_scheme_id, value, is_primary, source_record_id
        )
        values (?, ?, ?, ?, ?)
        """,
        (entity_id, row["identifier_scheme_id"], value, 1 if is_primary else 0, source_record_id),
    )
    return 1 if db.total_changes > before else 0


def apply_measurement_claims(
    db: sqlite3.Connection,
    entity_id: int,
    claims: dict[str, Any],
    source_record_id: int,
) -> int:
    count = 0
    for pid, measurement_type in sorted(MEASUREMENT_PROPERTY_TYPES.items()):
        for value in claims.get(pid, []) if isinstance(claims.get(pid), list) else []:
            normalized = normalize_measurement(measurement_type, value)
            if normalized is None:
                continue
            number, text, unit = normalized
            count += insert_measurement_if_missing(
                db,
                entity_id,
                measurement_type,
                number,
                text,
                unit,
                0.9,
                source_record_id,
            )
    return count


def normalize_measurement(measurement_type: str, value: Any) -> tuple[float | None, str | None, str | None] | None:
    if isinstance(value, dict):
        raw_amount = value.get("amount")
        source_unit = value.get("unit")
    else:
        raw_amount = value
        source_unit = None
    if isinstance(raw_amount, str):
        stripped = raw_amount.strip("+")
        try:
            amount = float(stripped)
        except ValueError:
            return None
    elif isinstance(raw_amount, (int, float)):
        amount = float(raw_amount)
    else:
        return None
    if measurement_type == "duration":
        unit, multiplier = DURATION_UNIT_MULTIPLIERS.get(source_unit, ("seconds" if source_unit in (None, "1") else str(source_unit), 1.0))
        return amount * multiplier, None, unit
    if measurement_type in {"height", "width", "depth", "thickness", "diameter"}:
        unit, multiplier = DIMENSION_UNIT_MULTIPLIERS.get(source_unit, (str(source_unit) if source_unit else None, 1.0))
        return amount * multiplier, None, unit
    if measurement_type == "weight":
        unit, multiplier = WEIGHT_UNIT_MULTIPLIERS.get(source_unit, (str(source_unit) if source_unit else None, 1.0))
        return amount * multiplier, None, unit
    if measurement_type in {"page_count", "track_count", "episode_count", "season_count"}:
        return amount, None, MEASUREMENT_TYPES_BY_CODE.get(measurement_type)
    return amount, None, str(source_unit) if source_unit else None


MEASUREMENT_TYPES_BY_CODE = {code: unit for code, _label, unit in MEASUREMENT_TYPES}


def insert_measurement_if_missing(
    db: sqlite3.Connection,
    entity_id: int,
    measurement_type: str,
    number: float | None,
    text: str | None,
    unit: str | None,
    confidence: float,
    source_record_id: int,
) -> int:
    type_row = db.execute(
        "select measurement_type_id from measurement_types where code = ?",
        (measurement_type,),
    ).fetchone()
    if type_row is None:
        return 0
    existing = db.execute(
        """
        select 1
        from entity_measurements
        where entity_id = ?
          and measurement_type_id = ?
          and coalesce(numeric_value, -999999999) = coalesce(?, -999999999)
          and coalesce(text_value, '') = coalesce(?, '')
          and coalesce(unit, '') = coalesce(?, '')
        limit 1
        """,
        (entity_id, type_row["measurement_type_id"], number, text, unit),
    ).fetchone()
    if existing:
        return 0
    db.execute(
        """
        insert into entity_measurements(
            entity_id, measurement_type_id, numeric_value, text_value,
            unit, confidence, source_record_id
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (entity_id, type_row["measurement_type_id"], number, text, unit, confidence, source_record_id),
    )
    return 1


def apply_concept_claims(
    db: sqlite3.Connection,
    entity_id: int,
    claims: dict[str, Any],
    text_lookup: dict[str, dict[str, Any]],
    source_record_id: int,
) -> int:
    count = 0
    for pid, (category, weight, confidence) in sorted(CONCEPT_PROPERTY_CATEGORIES.items()):
        for qid in claim_qids(claims.get(pid)):
            text = text_lookup.get(qid, {})
            label = text.get("label")
            if not isinstance(label, str) or not label:
                continue
            concept_id = ensure_concept(db, label, category, qid, f"wikidata_property:{pid}", confidence)
            count += insert_entity_concept_if_missing(db, entity_id, concept_id, weight, 0, confidence, source_record_id)
    return count


def ensure_concept(
    db: sqlite3.Connection,
    label: str,
    category: str,
    canonical_qid: str | None,
    rule: str,
    confidence: float,
) -> int:
    category_id = db.execute(
        "select concept_category_id from concept_categories where code = ?",
        (category,),
    ).fetchone()["concept_category_id"]
    row = db.execute(
        """
        select concept_id
        from concepts
        where concept_category_id = ? and label = ?
        """,
        (category_id, label),
    ).fetchone()
    if row:
        return int(row["concept_id"])
    canonical_entity_id = None
    if canonical_qid:
        qid_row = db.execute(
            """
            select i.entity_id
            from entity_identifiers i
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            where s.code = 'wikidata' and i.value = ?
            """,
            (canonical_qid,),
        ).fetchone()
        canonical_entity_id = int(qid_row["entity_id"]) if qid_row else None
    cursor = db.execute(
        """
        insert into concepts(
            label, concept_category_id, canonical_entity_id,
            namespace, value, classification_rule, confidence, review_recommended
        )
        values (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (label, category_id, canonical_entity_id, "wikidata", canonical_qid, rule, confidence),
    )
    return int(cursor.lastrowid)


def insert_entity_concept_if_missing(
    db: sqlite3.Connection,
    entity_id: int,
    concept_id: int,
    weight: int,
    polarity: int,
    confidence: float,
    source_record_id: int,
) -> int:
    before = db.total_changes
    db.execute(
        """
        insert or ignore into entity_concepts(
            entity_id, concept_id, weight, polarity, confidence, is_manual, source_record_id
        )
        values (?, ?, ?, ?, ?, 0, ?)
        """,
        (entity_id, concept_id, weight, polarity, confidence, source_record_id),
    )
    return 1 if db.total_changes > before else 0


def apply_relation_claims(
    db: sqlite3.Connection,
    entity_id: int,
    source_type_code: str | None,
    claims: dict[str, Any],
    qid_to_entity: dict[str, int],
    text_lookup: dict[str, dict[str, Any]],
    source_record_id: int,
) -> int:
    count = 0
    for pid in sorted(RELATION_PROPERTY_CODES):
        relation_code = relation_code_for_property(pid, source_type_code)
        if relation_code is None:
            continue
        for target_qid in claim_qids(claims.get(pid)):
            if target_qid == entity_wikidata_qid(db, entity_id):
                continue
            target_type = target_type_for_relation(relation_code)
            target_id = ensure_secondary_entity_for_qid(
                db,
                target_qid,
                target_type,
                text_lookup.get(target_qid),
                source_record_id,
                qid_to_entity,
            )
            count += upsert_relation(db, entity_id, target_id, relation_code, 50, 0, 0.9, source_record_id)
    return count


def entity_wikidata_qid(db: sqlite3.Connection, entity_id: int) -> str | None:
    row = db.execute(
        """
        select i.value
        from entity_identifiers i
        join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
        where i.entity_id = ? and s.code = 'wikidata'
        limit 1
        """,
        (entity_id,),
    ).fetchone()
    return row["value"] if row else None


def target_type_for_relation(relation_code: str) -> str:
    return RELATION_TARGET_TYPE_CODES.get(relation_code, "unknown")


def ensure_secondary_entity_for_qid(
    db: sqlite3.Connection,
    qid: str,
    type_code: str,
    text_info: dict[str, Any] | None,
    source_record_id: int,
    qid_to_entity: dict[str, int],
) -> int:
    existing = qid_to_entity.get(qid)
    if existing is not None:
        if type_code != "unknown":
            upsert_entity_type(db, existing, type_code, False, 0.8, source_record_id)
        apply_id_map_texts(db, existing, text_info, {})
        return existing
    label = text_info.get("label") if text_info else None
    if not isinstance(label, str) or not label:
        label = qid
    kind = TYPE_CODE_TO_ENTITY_KIND.get(type_code, ENTITY_KIND_UNKNOWN)
    family = entity_family_for_type_code(type_code)
    cursor = db.execute(
        """
        insert into entities(
            label, entity_kind, date_precision, is_catalogued,
            entity_family, completeness_status, confidence, review_state,
            created_at, updated_at
        )
        values (?, ?, 0, 0, ?, 'incomplete', 0.8, 'unreviewed', ?, ?)
        """,
        (label, kind, family, utc_now(), utc_now()),
    )
    entity_id = int(cursor.lastrowid)
    qid_to_entity[qid] = entity_id
    insert_identifier_if_missing(db, entity_id, "wikidata", qid, True, source_record_id)
    if type_code != "unknown":
        upsert_entity_type(db, entity_id, type_code, True, 0.8, source_record_id)
    apply_id_map_texts(db, entity_id, text_info, {})
    return entity_id


def upsert_relation(
    db: sqlite3.Connection,
    source_entity_id: int,
    target_entity_id: int,
    relation_code: str,
    weight: int,
    polarity: int,
    confidence: float,
    source_record_id: int,
) -> int:
    relation_row = db.execute(
        "select relation_type_id from relation_types where code = ?",
        (relation_code,),
    ).fetchone()
    if relation_row is None:
        return 0
    relation_type_id = int(relation_row["relation_type_id"])
    existing = db.execute(
        """
        select entity_relation_id
        from entity_relations
        where source_entity_id = ?
          and target_entity_id = ?
          and relation_type_id = ?
          and role_label is null
          and character_label is null
        limit 1
        """,
        (source_entity_id, target_entity_id, relation_type_id),
    ).fetchone()
    if existing:
        return 0
    associated = db.execute(
        """
        select r.entity_relation_id
        from entity_relations r
        join relation_types t on t.relation_type_id = r.relation_type_id
        where r.source_entity_id = ?
          and r.target_entity_id = ?
          and t.code = 'associated'
          and r.is_manual = 0
        limit 1
        """,
        (source_entity_id, target_entity_id),
    ).fetchone()
    if associated:
        db.execute(
            """
            update entity_relations
            set relation_type_id = ?, confidence = ?, source_record_id = ?
            where entity_relation_id = ?
            """,
            (relation_type_id, confidence, source_record_id, associated["entity_relation_id"]),
        )
        return 1
    before = db.total_changes
    db.execute(
        """
        insert or ignore into entity_relations(
            source_entity_id, target_entity_id, relation_type_id,
            weight, confidence, polarity, is_manual, source_record_id
        )
        values (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (source_entity_id, target_entity_id, relation_type_id, weight, confidence, polarity, source_record_id),
    )
    return 1 if db.total_changes > before else 0


def upsert_entity_type(
    db: sqlite3.Connection,
    entity_id: int,
    type_code: str,
    prefer_primary: bool,
    confidence: float,
    source_record_id: int,
) -> bool:
    type_row = db.execute(
        "select entity_type_id, family from entity_type_definitions where code = ?",
        (type_code,),
    ).fetchone()
    if type_row is None:
        return False
    type_id = int(type_row["entity_type_id"])
    existing = db.execute(
        "select is_primary, confidence from entity_types where entity_id = ? and entity_type_id = ?",
        (entity_id, type_id),
    ).fetchone()
    changed = False
    made_primary = bool(existing and int(existing["is_primary"]))
    if existing is None:
        db.execute(
            """
            insert into entity_types(entity_id, entity_type_id, is_primary, confidence, source_record_id)
            values (?, ?, ?, ?, ?)
            """,
            (entity_id, type_id, 1 if prefer_primary else 0, confidence, source_record_id),
        )
        changed = True
        made_primary = prefer_primary
    elif prefer_primary and not int(existing["is_primary"]):
        db.execute(
            """
            update entity_types
            set is_primary = 1,
                confidence = max(coalesce(confidence, 0), ?),
                source_record_id = coalesce(source_record_id, ?)
            where entity_id = ? and entity_type_id = ?
            """,
            (confidence, source_record_id, entity_id, type_id),
        )
        changed = True
    if prefer_primary:
        current = db.execute(
            """
            select d.code
            from entity_types t
            join entity_type_definitions d on d.entity_type_id = t.entity_type_id
            where t.entity_id = ? and t.is_primary = 1 and d.code <> ?
            order by coalesce(t.confidence, 0) desc, d.code
            limit 1
            """,
            (entity_id, type_code),
        ).fetchone()
        if current is None or current["code"] in {"unknown", "other_creative_work"}:
            db.execute(
                "update entity_types set is_primary = 0 where entity_id = ? and entity_type_id <> ?",
                (entity_id, type_id),
            )
            db.execute(
                "update entity_types set is_primary = 1 where entity_id = ? and entity_type_id = ?",
                (entity_id, type_id),
            )
            made_primary = True
        kind = TYPE_CODE_TO_ENTITY_KIND.get(type_code, ENTITY_KIND_UNKNOWN)
        family = entity_family_for_type_code(type_code)
        if made_primary:
            db.execute(
                """
                update entities
                set entity_kind = case when entity_kind = 0 or ? != 0 then ? else entity_kind end,
                    entity_family = case
                        when entity_family is null or entity_family = 'unknown' or ? != 'unknown' then ?
                        else entity_family
                    end,
                    updated_at = ?
                where entity_id = ?
                """,
                (kind, kind, family, family, utc_now(), entity_id),
            )
    return changed


def entity_family_for_type_code(type_code: str) -> str:
    if type_code in {"person"}:
        return "person"
    if type_code in {"creative_group", "music_group", "band"}:
        return "group"
    if type_code in {
        "organization",
        "company",
        "production_company",
        "film_studio",
        "record_label",
        "publisher",
        "broadcaster",
        "game_studio",
        "developer",
        "distributor",
    }:
        return "organization"
    if type_code in {"genre"}:
        return "concept"
    if type_code == "unknown":
        return "unknown"
    return "work"


def update_entity_label_if_missing(db: sqlite3.Connection, entity_id: int, label: str) -> bool:
    row = db.execute("select label from entities where entity_id = ?", (entity_id,)).fetchone()
    if row is None:
        return False
    existing = row["label"] or ""
    if existing and not QID_RE.fullmatch(existing):
        return False
    db.execute(
        "update entities set label = ?, updated_at = ? where entity_id = ?",
        (label, utc_now(), entity_id),
    )
    return True


def update_entity_description_if_missing(db: sqlite3.Connection, entity_id: int, description: str) -> bool:
    row = db.execute("select short_description from entities where entity_id = ?", (entity_id,)).fetchone()
    if row is None or row["short_description"]:
        return False
    db.execute(
        "update entities set short_description = ?, updated_at = ? where entity_id = ?",
        (description, utc_now(), entity_id),
    )
    return True


def update_entity_image_if_missing(db: sqlite3.Connection, entity_id: int, image: str) -> bool:
    row = db.execute("select image_ref from entities where entity_id = ?", (entity_id,)).fetchone()
    if row is None or row["image_ref"]:
        return False
    db.execute(
        "update entities set image_ref = ?, updated_at = ? where entity_id = ?",
        (image, utc_now(), entity_id),
    )
    return True


def insert_text_if_missing(
    db: sqlite3.Connection,
    entity_id: int,
    text_kind: str,
    language: str | None,
    value: str,
    is_primary: bool,
    source_record_id: int,
) -> bool:
    if not value:
        return False
    existing = db.execute(
        """
        select 1
        from entity_texts
        where entity_id = ?
          and text_kind = ?
          and coalesce(language, '') = coalesce(?, '')
          and value = ?
        limit 1
        """,
        (entity_id, text_kind, language, value),
    ).fetchone()
    if existing:
        return False
    db.execute(
        """
        insert into entity_texts(entity_id, text_kind, language, value, is_primary, source_record_id)
        values (?, ?, ?, ?, ?, ?)
        """,
        (entity_id, text_kind, language, value, 1 if is_primary else 0, source_record_id),
    )
    return True


def cached_source_record(
    db: sqlite3.Connection,
    cache: dict[tuple[str, str, str], int],
    *,
    data_source_code: str,
    external_id: str | None = None,
    local_path: str | None = None,
    payload_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    key = (data_source_code, external_id or "", local_path or "")
    if key not in cache:
        cache[key] = ensure_source_record(
            db,
            data_source_code=data_source_code,
            external_id=external_id,
            local_path=local_path,
            payload_hash=payload_hash,
            metadata=metadata,
        )
    return cache[key]


def relative_local_path(value: str) -> str:
    marker = "/layers/"
    if marker in value:
        return "layers/" + value.split(marker, 1)[1]
    return value


def clear_migrated_concept_manual_flags(db: sqlite3.Connection) -> int:
    before = db.total_changes
    db.execute(
        """
        update entity_concepts
        set is_manual = 0
        where is_manual = 1
          and source_record_id in (
            select sr.source_record_id
            from source_records sr
            join data_sources ds on ds.data_source_id = sr.data_source_id
            where ds.code = 'legacy_database'
          )
        """
    )
    return db.total_changes - before


def reclassify_existing_concepts(db: sqlite3.Connection) -> int:
    category_ids = definition_ids(db, "concept_categories", "concept_category_id")
    changed = 0
    for row in db.execute(
        """
        select c.concept_id, c.concept_category_id, c.classification_rule,
               t.tag_id, t.name, t.description, t.namespace, t.value, t.tag_kind
        from concepts c
        join tags t on t.tag_id = c.legacy_tag_id
        order by c.concept_id
        """
    ).fetchall():
        category, rule, confidence, review = classify_tag(row)
        category_id = category_ids[category]
        if int(row["concept_category_id"]) == category_id and row["classification_rule"] == rule:
            continue
        db.execute(
            """
            update concepts
            set concept_category_id = ?,
                classification_rule = ?,
                confidence = ?,
                review_recommended = ?
            where concept_id = ?
            """,
            (category_id, rule, confidence, 1 if review else 0, row["concept_id"]),
        )
        changed += 1
    return changed


def refresh_entity_cache_fields(db: sqlite3.Connection) -> None:
    db.execute(
        """
        update entities
        set completeness_status = case
                when label glob 'Q[0-9]*' or (is_catalogued = 1 and release_date is null) or entity_kind = 0
                    then 'incomplete'
                else 'partial'
            end,
            entity_family = coalesce(entity_family, 'unknown'),
            updated_at = coalesce(updated_at, ?)
        """,
        (utc_now(),),
    )


def enrichment_coverage_counts(db: sqlite3.Connection) -> dict[str, Any]:
    return {
        "entities": table_count(db, "entities"),
        "catalog": db.execute("select count(*) from entities where is_catalogued = 1").fetchone()[0],
        "rawQidLabels": db.execute("select count(*) from entities where label glob 'Q[0-9]*'").fetchone()[0],
        "catalogMissingDates": db.execute(
            "select count(*) from entities where is_catalogued = 1 and release_date is null"
        ).fetchone()[0],
        "unknownKinds": db.execute("select count(*) from entities where entity_kind = 0").fetchone()[0],
        "descriptions": db.execute("select count(*) from entities where short_description is not null").fetchone()[0],
        "aliases": db.execute("select count(*) from entity_texts where text_kind = 'alias'").fetchone()[0],
        "entityDates": table_count(db, "entity_dates"),
        "measurements": table_count(db, "entity_measurements"),
        "advisories": table_count(db, "entity_advisories"),
        "ratings": table_count(db, "entity_age_ratings"),
        "restrictions": table_count(db, "entity_restrictions"),
        "externalIdentifiers": table_count(db, "entity_identifiers"),
        "genericAssociatedRelations": db.execute(
            """
            select count(*)
            from entity_relations r
            join relation_types t on t.relation_type_id = r.relation_type_id
            where t.code = 'associated'
            """
        ).fetchone()[0],
        "entityTypeCoverage": rows_as_dicts(
            db.execute(
                """
                select d.code, d.family, count(*) as count
                from entity_types t
                join entity_type_definitions d on d.entity_type_id = t.entity_type_id
                group by d.code, d.family
                order by count desc, d.code
                """
            )
        ),
        "conceptClassification": rows_as_dicts(
            db.execute(
                """
                select cc.code, count(*) as count
                from concepts c
                join concept_categories cc on cc.concept_category_id = c.concept_category_id
                group by cc.code
                order by count desc, cc.code
                """
            )
        ),
    }


def table_count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"select count(*) from {table}").fetchone()[0])


def source_usage_counts(db: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_as_dicts(
        db.execute(
            """
            select ds.code, count(sr.source_record_id) as sourceRecords
            from data_sources ds
            left join source_records sr on sr.data_source_id = ds.data_source_id
            group by ds.code
            order by ds.code
            """
        )
    )


def fields_not_populated(db: sqlite3.Connection) -> list[str]:
    missing = []
    if table_count(db, "entity_advisories") == 0:
        missing.append("entity_advisories: no deterministic local advisory source applied")
    if table_count(db, "entity_age_ratings") == 0:
        missing.append("entity_age_ratings: no supported local rating mapping applied")
    if table_count(db, "entity_restrictions") == 0:
        missing.append("entity_restrictions: no supported local restriction mapping applied")
    if db.execute("select count(*) from entity_texts where text_kind = 'alias'").fetchone()[0] == 0:
        missing.append("entity_texts.alias: local id map did not provide aliases for selected QIDs")
    return missing


def enrich_remote(
    project_root: Path,
    db_path: Path,
    *,
    qids: set[str] | None = None,
    limit: int | None = None,
    offline: bool = True,
    refresh_cache: bool = False,
) -> dict[str, Any]:
    paths = ensure_workspace(project_root)
    selected = sorted(qids or unresolved_remote_qids(db_path))
    if limit is not None:
        selected = selected[:limit]
    report = {
        "requests": [],
        "offline": offline,
        "updated": 0,
        "failed": 0,
        "cached": 0,
        "qids": len(selected),
        "note": "remote fallback caches raw batched responses; applying values requires explicit source-specific enrichment",
    }
    cache_dir = paths.cache / "wikidata"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for batch in batched(selected, 50):
        cache_key = hashlib.sha256("|".join(batch).encode("utf-8")).hexdigest()
        cache_path = cache_dir / f"{cache_key}.json"
        request_record = {
            "qids": batch,
            "cache": str(cache_path),
            "status": "cache_hit" if cache_path.exists() and not refresh_cache else "pending",
        }
        if cache_path.exists() and not refresh_cache:
            report["cached"] += 1
            report["requests"].append(request_record)
            continue
        if offline:
            request_record["status"] = "offline_missing_cache"
            report["failed"] += 1
            report["requests"].append(request_record)
            continue
        try:
            body = fetch_wikidata_batch(batch)
            cache_path.write_text(body, encoding="utf-8")
            request_record["status"] = "fetched"
            report["cached"] += 1
        except Exception as exc:
            request_record["status"] = "failed"
            request_record["error"] = str(exc)
            report["failed"] += 1
        report["requests"].append(request_record)
    write_json(paths.reports / "remote_requests.json", report["requests"])
    return report


def unresolved_remote_qids(db_path: Path) -> set[str]:
    if not db_path.is_file():
        return set()
    db = sqlite3.connect(db_path)
    try:
        if not table_exists(db, "entity_identifiers"):
            return set()
        return {
            row[0]
            for row in db.execute(
                """
                select i.value
                from entity_identifiers i
                join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
                join entities e on e.entity_id = i.entity_id
                where s.code = 'wikidata'
                  and (
                    e.label glob 'Q[0-9]*'
                    or e.entity_family = 'unknown'
                    or (e.is_catalogued = 1 and e.release_date is null)
                  )
                order by i.value
                """
            )
        }
    finally:
        db.close()


def table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table,),
    ).fetchone() is not None


def batched(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def fetch_wikidata_batch(qids: list[str]) -> str:
    params = urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "format": "json",
            "props": "labels|descriptions|aliases|claims",
            "languages": "en|mul",
        }
    )
    request = urllib.request.Request(
        f"https://www.wikidata.org/w/api.php?{params}",
        headers={"User-Agent": "art-islands-db-v2-migration/0.1"},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(str(last_error) if last_error else "wikidata request failed")
