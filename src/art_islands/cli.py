from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import batch as batch_module
from . import v2 as v2_module
from .model import (
    ENTITY_KIND_FILM,
    ENTITY_KIND_GAME,
    ENTITY_KIND_MUSIC_RELEASE,
    ENTITY_KIND_UNKNOWN,
    ENTITY_KIND_WORK,
    EntityMetadata,
    QID_RE,
    REF_KIND_DISCOGS,
    REF_KIND_IMDB,
    REF_KIND_MUSICBRAINZ,
    REF_KIND_TMDB,
    REF_KIND_WIKIDATA,
    connect_art,
    default_art_layers,
    export_static_data,
    first_string,
    load_id_map_labels,
    load_settings,
    parse_wikidata_date,
    save_settings,
    scan_layer_metadata,
    settings_with_defaults,
)


FIELD_NAMES = ("label", "date", "kind", "image", "refs")
CONFIG_KEYS = {
    "recommendation.like-weight": ("likeWeight", "float"),
    "recommendation.dislike-weight": ("dislikeWeight", "float"),
    "recommendation.limit": ("limit", "int"),
}
SCHEME_CODE_BY_REF_KIND = {
    REF_KIND_WIKIDATA: "wikidata",
    REF_KIND_IMDB: "imdb_title",
    REF_KIND_TMDB: "tmdb_movie",
    REF_KIND_MUSICBRAINZ: "musicbrainz_release_group",
    REF_KIND_DISCOGS: "discogs_release",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_db_path() -> Path:
    return project_root() / "data" / "art-islands.sqlite"


def default_output_path() -> Path:
    return project_root() / "public" / "data"


def default_v2_db_path() -> Path:
    return default_db_path()


def default_v2_output_path() -> Path:
    return project_root() / "public" / "data" / "v2"


def default_settings_path() -> Path:
    return project_root() / "data" / "settings.json"


def default_source_root() -> Path:
    return project_root().parent


def default_id_map_path() -> Path:
    return default_source_root() / "layers" / "id_map.slow.partial.jsonl"


def resolved_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def parse_fields(value: str) -> tuple[str, ...]:
    fields = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [field for field in fields if field not in FIELD_NAMES]
    if not fields or unknown:
        allowed = ",".join(FIELD_NAMES)
        raise argparse.ArgumentTypeError(f"fields must be a comma list from: {allowed}")
    return fields


def parse_weight(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("weight must be an integer from 0 to 100") from exc
    if parsed < 0 or parsed > 100:
        raise argparse.ArgumentTypeError("weight must be an integer from 0 to 100")
    return parsed


def parse_polarity(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("polarity must be -1, 0, or 1") from exc
    if parsed not in {-1, 0, 1}:
        raise argparse.ArgumentTypeError("polarity must be -1, 0, or 1")
    return parsed


def parse_positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a non-negative number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative number")
    return parsed


def parse_positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def enrichment_layer_paths(source_root: Path) -> list[Path]:
    layers = default_art_layers(source_root)
    other = source_root / "layers" / "other_creative_work.jsonl"
    if other.is_file():
        layers.append(other)
    return layers


def command_export(args) -> None:
    if args.version == 2:
        db_path = default_v2_db_path() if args.db == default_db_path() else args.db
        output_path = default_v2_output_path() if args.output == default_output_path() else args.output
        root_result = export_static_data(db_path, default_output_path(), args.settings)
        result = v2_module.export_v2_static_data(db_path, output_path, args.settings)
        result = {**root_result, **{f"v2_{key}": value for key, value in result.items()}}
        args.output = output_path
    else:
        result = export_static_data(args.db, args.output, args.settings)
    for key, value in result.items():
        print(f"{key}={value}")
    print(f"output={args.output}")


def _fail_batch(error: batch_module.BatchError) -> None:
    for message in error.errors:
        print(f"error: {message}")
    raise SystemExit(1)


def command_batch_from_issue(args) -> None:
    body = args.body_file.read_text(encoding="utf-8")
    try:
        source = batch_module.extract_batch_source(body)
        if source.kind == "inline":
            text = source.text or ""
        else:
            text = batch_module.download_attachment(source.url or "")
        parsed = batch_module.parse_batch_text(text)
    except batch_module.BatchError as exc:
        _fail_batch(exc)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"source={source.kind} operations={len(parsed.operations)} output={args.output}")


def command_batch_validate(args) -> None:
    text = args.file.read_text(encoding="utf-8")
    db = connect_art(args.db)
    try:
        parsed = batch_module.parse_batch_text(text)
        batch_module.validate_batch(db, parsed)
    except batch_module.BatchError as exc:
        _fail_batch(exc)
        return
    finally:
        db.close()
    print(f"valid=1 operations={len(parsed.operations)}")


def command_batch_apply(args) -> None:
    text = args.file.read_text(encoding="utf-8")
    db = connect_art(args.db)
    try:
        parsed = batch_module.parse_batch_text(text)
        batch_module.validate_batch(db, parsed)
        db.execute("begin")
        try:
            result = batch_module.apply_batch(db, parsed)
            db.commit()
        except Exception:
            db.rollback()
            raise
    except batch_module.BatchError as exc:
        _fail_batch(exc)
        return
    finally:
        db.close()
    print(json.dumps({"operations": len(parsed.operations), **result.as_dict()}, sort_keys=True))


def command_serve_static(args) -> None:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(args.root),
    )
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"serving=http://{args.host}:{args.port}", flush=True)
        httpd.serve_forever()


def command_config_show(args) -> None:
    print(json.dumps(load_settings(args.settings), ensure_ascii=False, indent=2, sort_keys=True))


def command_config_set(args) -> None:
    json_key, value_kind = CONFIG_KEYS[args.key]
    try:
        if value_kind == "int":
            parsed_value = parse_positive_int(args.value)
        else:
            parsed_value = parse_positive_float(args.value)
    except argparse.ArgumentTypeError as exc:
        raise SystemExit(str(exc)) from exc
    settings = load_settings(args.settings)
    settings["recommendation"][json_key] = parsed_value
    save_settings(args.settings, settings)
    print(f"{args.key}={settings['recommendation'][json_key]}")


def command_db_v2_export(args) -> None:
    result = v2_module.export_v2_static_data(args.db, args.output, args.settings)
    for key, value in result.items():
        print(f"{key}={value}")
    print(f"output={args.output}")


def command_db_v2_validate(args) -> None:
    result = v2_module.validate_v2_database(project_root(), args.source_db, args.db)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["ok"]:
        raise SystemExit(1)


def identifier_scheme_id(db: sqlite3.Connection, code: str) -> int:
    row = db.execute(
        "select identifier_scheme_id from identifier_schemes where code = ?",
        (code,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"identifier scheme is not configured: {code}")
    return int(row["identifier_scheme_id"])


def command_concept_set(args) -> None:
    if args.weight is None and args.polarity is None:
        raise SystemExit("concept set requires --weight, --polarity, or both")

    db = connect_art(args.db)
    try:
        entity = db.execute(
            "select 1 from entities where entity_id = ?",
            (args.entity,),
        ).fetchone()
        if entity is None:
            raise SystemExit(f"unknown entity_id: {args.entity}")

        concept = db.execute(
            "select 1 from concepts where concept_id = ?",
            (args.concept,),
        ).fetchone()
        if concept is None:
            raise SystemExit(f"unknown concept_id: {args.concept}")

        entity_concept = db.execute(
            "select 1 from entity_concepts where entity_id = ? and concept_id = ?",
            (args.entity, args.concept),
        ).fetchone()
        if entity_concept is None:
            raise SystemExit("entity_concepts row does not exist")

        assignments: list[str] = []
        values: list[int] = []
        if args.weight is not None:
            assignments.append("weight = ?")
            values.append(args.weight)
        if args.polarity is not None:
            assignments.append("polarity = ?")
            values.append(args.polarity)
        values.extend([args.entity, args.concept])
        db.execute(
            f"""
            update entity_concepts
            set {", ".join(assignments)}
            where entity_id = ? and concept_id = ?
            """,
            values,
        )
        db.commit()
    finally:
        db.close()

    changed = []
    if args.weight is not None:
        changed.append(f"weight={args.weight}")
    if args.polarity is not None:
        changed.append(f"polarity={args.polarity}")
    print("updated=1 " + " ".join(changed))


def command_enrich(args) -> None:
    fields = args.fields or FIELD_NAMES
    db = connect_art(args.db)
    try:
        targets = select_enrichment_targets(db, args, fields)
        qids = {row["qid"] for row in targets}
        local_metadata = scan_layer_metadata(
            enrichment_layer_paths(args.source_root),
            qids,
        )
        local_labels = load_id_map_labels(args.id_map, qids)

        counts = {"updated": 0, "skipped": 0, "unresolved": 0, "failed": 0}
        for row in targets:
            qid = row["qid"]
            metadata = merged_metadata(
                local_metadata.get(qid, EntityMetadata()),
                EntityMetadata(label=local_labels.get(qid, "")),
            )
            needs_remote = entity_needs_remote(db, row, metadata, fields, args.force)
            if needs_remote:
                try:
                    remote = fetch_wikidata_metadata(qid)
                except Exception:
                    counts["failed"] += 1
                    remote = EntityMetadata()
                metadata = merged_metadata(metadata, remote)

            changed, unresolved = apply_enrichment_metadata(
                db,
                row,
                metadata,
                fields,
                args.force,
            )
            if changed:
                counts["updated"] += 1
            elif unresolved:
                counts["unresolved"] += 1
            else:
                counts["skipped"] += 1
        db.commit()
    finally:
        db.close()

    print(
        " ".join(
            f"{key}={value}"
            for key, value in (
                ("updated", counts["updated"]),
                ("skipped", counts["skipped"]),
                ("unresolved", counts["unresolved"]),
                ("failed", counts["failed"]),
            )
        )
    )


def select_enrichment_targets(
    db: sqlite3.Connection,
    args,
    fields: tuple[str, ...],
) -> list[sqlite3.Row]:
    rows = db.execute(
        """
        select e.*, i.value as qid
        from entities e
        join entity_identifiers i on i.entity_id = e.entity_id
        join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
         and s.code = 'wikidata'
        order by e.entity_id
        """
    ).fetchall()

    if args.entity is not None:
        selected = [row for row in rows if row["entity_id"] == args.entity]
        if not selected:
            raise SystemExit(f"unknown entity_id with Wikidata ref: {args.entity}")
        return selected

    if args.qid is not None:
        if not QID_RE.fullmatch(args.qid):
            raise SystemExit(f"invalid QID: {args.qid}")
        selected = [row for row in rows if row["qid"] == args.qid]
        if not selected:
            raise SystemExit(f"QID is not present in the database: {args.qid}")
        return selected

    return [
        row
        for row in rows
        if any(entity_field_missing(db, row, field) for field in fields)
    ]


def entity_field_missing(db: sqlite3.Connection, row: sqlite3.Row, field: str) -> bool:
    if field == "label":
        label = row["label"] or ""
        return not label or bool(QID_RE.fullmatch(label))
    if field == "date":
        return not row["release_date"]
    if field == "kind":
        return int(row["entity_kind"]) == ENTITY_KIND_UNKNOWN
    if field == "image":
        return not row["image_ref"]
    if field == "refs":
        count = db.execute(
            """
            select count(*)
            from entity_identifiers i
            join identifier_schemes s on s.identifier_scheme_id = i.identifier_scheme_id
            where i.entity_id = ? and s.code <> 'wikidata'
            """,
            (row["entity_id"],),
        ).fetchone()[0]
        return int(count) == 0
    return False


def entity_needs_remote(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    metadata: EntityMetadata,
    fields: tuple[str, ...],
    force: bool,
) -> bool:
    for field in fields:
        if not force and not entity_field_missing(db, row, field):
            continue
        if not metadata_supplies_field(metadata, field):
            return True
    return False


def metadata_supplies_field(metadata: EntityMetadata, field: str) -> bool:
    if field == "label":
        return bool(metadata.label and not QID_RE.fullmatch(metadata.label))
    if field == "date":
        return bool(metadata.release_date)
    if field == "kind":
        return metadata.entity_kind != ENTITY_KIND_UNKNOWN
    if field == "image":
        return bool(metadata.image_ref)
    if field == "refs":
        return any(ref_kind != REF_KIND_WIKIDATA for ref_kind, _ in metadata.refs)
    return False


def merged_metadata(primary: EntityMetadata, fallback: EntityMetadata) -> EntityMetadata:
    refs: dict[int, str] = {}
    for ref_kind, ref_value in primary.refs + fallback.refs:
        refs.setdefault(ref_kind, ref_value)
    return EntityMetadata(
        label=primary.label or fallback.label,
        entity_kind=(
            primary.entity_kind
            if primary.entity_kind != ENTITY_KIND_UNKNOWN
            else fallback.entity_kind
        ),
        release_date=primary.release_date or fallback.release_date,
        date_precision=primary.date_precision or fallback.date_precision,
        image_ref=primary.image_ref or fallback.image_ref,
        refs=tuple(sorted(refs.items())),
        links=primary.links or fallback.links,
    )


def apply_enrichment_metadata(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    metadata: EntityMetadata,
    fields: tuple[str, ...],
    force: bool,
) -> tuple[bool, bool]:
    updates: dict[str, Any] = {}
    unresolved = False

    if "label" in fields and (force or entity_field_missing(db, row, "label")):
        if metadata.label and not QID_RE.fullmatch(metadata.label):
            updates["label"] = metadata.label
        else:
            unresolved = True

    if "date" in fields and (force or entity_field_missing(db, row, "date")):
        if metadata.release_date:
            updates["release_date"] = metadata.release_date
            updates["date_precision"] = metadata.date_precision
        else:
            unresolved = True

    if "kind" in fields and (force or entity_field_missing(db, row, "kind")):
        if metadata.entity_kind != ENTITY_KIND_UNKNOWN:
            updates["entity_kind"] = metadata.entity_kind
        else:
            unresolved = True

    if "image" in fields and (force or entity_field_missing(db, row, "image")):
        if metadata.image_ref:
            updates["image_ref"] = metadata.image_ref
        else:
            unresolved = True

    changed = False
    if updates:
        assignments = ", ".join(f"{name} = ?" for name in updates)
        db.execute(
            f"update entities set {assignments} where entity_id = ?",
            [*updates.values(), row["entity_id"]],
        )
        changed = True

    if "refs" in fields and (force or entity_field_missing(db, row, "refs")):
        external_refs = [
            (ref_kind, ref_value)
            for ref_kind, ref_value in metadata.refs
            if ref_kind != REF_KIND_WIKIDATA
        ]
        if not external_refs:
            unresolved = True
        for ref_kind, ref_value in external_refs:
            scheme_code = SCHEME_CODE_BY_REF_KIND.get(ref_kind)
            if scheme_code is None:
                continue
            scheme_id = identifier_scheme_id(db, scheme_code)
            before = db.total_changes
            db.execute(
                """
                insert into entity_identifiers(entity_id, identifier_scheme_id, value, is_primary)
                values (?, ?, ?, 0)
                on conflict(identifier_scheme_id, value) do nothing
                """,
                (row["entity_id"], scheme_id, ref_value),
            )
            changed = changed or db.total_changes > before

    return changed, unresolved


def fetch_wikidata_metadata(qid: str) -> EntityMetadata:
    if not QID_RE.fullmatch(qid):
        return EntityMetadata()
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "art-islands-cli/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc

    entity = payload.get("entities", {}).get(qid)
    if not isinstance(entity, dict):
        return EntityMetadata()
    return metadata_from_wikidata_entity(qid, entity)


def metadata_from_wikidata_entity(qid: str, entity: dict[str, Any]) -> EntityMetadata:
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        claims = {}
    release_date, date_precision = best_remote_date(claims)
    return EntityMetadata(
        label=remote_label(entity),
        entity_kind=remote_kind(claims),
        release_date=release_date,
        date_precision=date_precision,
        image_ref=first_string(remote_string_claims(claims, "P18")),
        refs=remote_refs(qid, claims),
    )


def remote_label(entity: dict[str, Any]) -> str:
    labels = entity.get("labels")
    if not isinstance(labels, dict):
        return ""
    for language in ("en", "mul", "de", "ru"):
        row = labels.get(language)
        if isinstance(row, dict) and isinstance(row.get("value"), str) and row["value"]:
            return row["value"]
    for row in labels.values():
        if isinstance(row, dict) and isinstance(row.get("value"), str) and row["value"]:
            return row["value"]
    return ""


def remote_string_claims(claims: dict[str, Any], pid: str) -> list[str]:
    values: list[str] = []
    for claim in claims.get(pid, []):
        if not isinstance(claim, dict):
            continue
        value = (
            claim.get("mainsnak", {})
            .get("datavalue", {})
            .get("value")
        )
        if isinstance(value, str) and value:
            values.append(value)
    return values


def remote_time_claims(claims: dict[str, Any], pid: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for claim in claims.get(pid, []):
        if not isinstance(claim, dict):
            continue
        value = (
            claim.get("mainsnak", {})
            .get("datavalue", {})
            .get("value")
        )
        if isinstance(value, dict):
            values.append(value)
    return values


def remote_qid_claims(claims: dict[str, Any], pid: str) -> list[str]:
    values: list[str] = []
    for claim in claims.get(pid, []):
        if not isinstance(claim, dict):
            continue
        value = (
            claim.get("mainsnak", {})
            .get("datavalue", {})
            .get("value")
        )
        if isinstance(value, dict):
            raw = value.get("id")
            if isinstance(raw, str) and QID_RE.fullmatch(raw):
                values.append(raw)
    return values


def best_remote_date(claims: dict[str, Any]) -> tuple[str | None, int]:
    candidates: list[tuple[str, int]] = []
    for pid in ("P577", "P571", "P580", "P585"):
        for value in remote_time_claims(claims, pid):
            parsed = parse_wikidata_date(value)
            if parsed is not None:
                candidates.append(parsed)
    if not candidates:
        return None, 0
    return min(candidates, key=lambda item: (item[0], -item[1]))


def remote_kind(claims: dict[str, Any]) -> int:
    kinds = set(remote_qid_claims(claims, "P31")) | set(remote_qid_claims(claims, "P279"))
    if kinds & {"Q11424", "Q506240"}:
        return ENTITY_KIND_FILM
    if kinds & {"Q482994", "Q134556", "Q2031291", "Q7366", "Q2188189"}:
        return ENTITY_KIND_MUSIC_RELEASE
    if kinds & {"Q7889", "Q7058673"}:
        return ENTITY_KIND_GAME
    if kinds & {
        "Q571",
        "Q7725634",
        "Q47461344",
        "Q3305213",
        "Q860861",
        "Q125191",
        "Q1004",
        "Q386724",
    }:
        return ENTITY_KIND_WORK
    return ENTITY_KIND_UNKNOWN


def remote_refs(qid: str, claims: dict[str, Any]) -> tuple[tuple[int, str], ...]:
    refs: dict[int, str] = {REF_KIND_WIKIDATA: qid}
    for ref_kind, pids in (
        (REF_KIND_IMDB, ("P345",)),
        (REF_KIND_TMDB, ("P4947", "P4983")),
        (REF_KIND_MUSICBRAINZ, ("P436", "P435", "P966", "P434")),
        (REF_KIND_DISCOGS, ("P1954", "P2205", "P2206", "P1953")),
    ):
        for pid in pids:
            value = first_string(remote_string_claims(claims, pid))
            if value:
                refs.setdefault(ref_kind, value)
                break
    return tuple(sorted(refs.items()))


def add_common_export_args(target: argparse.ArgumentParser) -> None:
    target.add_argument("--db", type=resolved_path, default=default_db_path())
    target.add_argument("--output", type=resolved_path, default=default_output_path())
    target.add_argument("--settings", type=resolved_path, default=default_settings_path())


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="art-islands")
    sub = root.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export")
    add_common_export_args(export)
    export.add_argument("--version", type=int, choices=(1, 2), default=2)
    export.set_defaults(function=command_export)

    enrich = sub.add_parser("enrich")
    enrich_target = enrich.add_mutually_exclusive_group(required=True)
    enrich_target.add_argument("--all-missing", action="store_true")
    enrich_target.add_argument("--entity", type=int)
    enrich_target.add_argument("--qid")
    enrich.add_argument("--fields", type=parse_fields)
    enrich.add_argument("--force", action="store_true")
    enrich.add_argument("--db", type=resolved_path, default=default_db_path())
    enrich.add_argument("--source-root", type=resolved_path, default=default_source_root())
    enrich.add_argument("--id-map", type=resolved_path, default=default_id_map_path())
    enrich.set_defaults(function=command_enrich)

    concept = sub.add_parser("concept")
    concept_sub = concept.add_subparsers(dest="concept_command", required=True)
    concept_set = concept_sub.add_parser("set")
    concept_set.add_argument("--entity", type=int, required=True)
    concept_set.add_argument("--concept", type=int, required=True)
    concept_set.add_argument("--weight", type=parse_weight)
    concept_set.add_argument("--polarity", type=parse_polarity)
    concept_set.add_argument("--db", type=resolved_path, default=default_db_path())
    concept_set.set_defaults(function=command_concept_set)

    batch = sub.add_parser("batch")
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    batch_from_issue = batch_sub.add_parser("from-issue")
    batch_from_issue.add_argument("--body-file", type=resolved_path, required=True)
    batch_from_issue.add_argument("--output", type=resolved_path, required=True)
    batch_from_issue.set_defaults(function=command_batch_from_issue)
    batch_validate = batch_sub.add_parser("validate")
    batch_validate.add_argument("--file", type=resolved_path, required=True)
    batch_validate.add_argument("--db", type=resolved_path, default=default_db_path())
    batch_validate.set_defaults(function=command_batch_validate)
    batch_apply = batch_sub.add_parser("apply")
    batch_apply.add_argument("--file", type=resolved_path, required=True)
    batch_apply.add_argument("--db", type=resolved_path, default=default_db_path())
    batch_apply.set_defaults(function=command_batch_apply)

    config = sub.add_parser("config")
    config.add_argument("--settings", type=resolved_path, default=default_settings_path())
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_show = config_sub.add_parser("show")
    config_show.set_defaults(function=command_config_show)
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key", choices=sorted(CONFIG_KEYS))
    config_set.add_argument("value")
    config_set.set_defaults(function=command_config_set)

    db_v2 = sub.add_parser("db-v2")
    db_v2_sub = db_v2.add_subparsers(dest="db_v2_command", required=True)

    db_v2_export = db_v2_sub.add_parser("export")
    db_v2_export.add_argument("--db", type=resolved_path, default=default_v2_db_path())
    db_v2_export.add_argument("--output", type=resolved_path, default=default_v2_output_path())
    db_v2_export.add_argument("--settings", type=resolved_path, default=default_settings_path())
    db_v2_export.set_defaults(function=command_db_v2_export)

    db_v2_validate = db_v2_sub.add_parser("validate")
    db_v2_validate.add_argument("--source-db", type=resolved_path, default=default_db_path())
    db_v2_validate.add_argument("--db", type=resolved_path, default=default_v2_db_path())
    db_v2_validate.set_defaults(function=command_db_v2_validate)

    serve = sub.add_parser("serve-static")
    serve.add_argument("--root", type=resolved_path, default=Path("public"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8090)
    serve.set_defaults(function=command_serve_static)

    return root


def main() -> None:
    args = parser().parse_args()
    if hasattr(args, "settings"):
        settings_with_defaults(load_settings(args.settings))
    args.function(args)
