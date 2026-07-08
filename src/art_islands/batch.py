"""Declarative data-correction batches submitted through GitHub issues.

A batch is a UTF-8 JSON or JSONL document describing entity corrections.
Batch content is data only: it is parsed, validated against the SQLite
database, and applied through fixed parameterized statements. Nothing in a
batch is ever executed as code, shell, or SQL text.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

BATCH_VERSION = 1
MAX_OPERATIONS = 1000
MAX_BATCH_BYTES = 1_000_000

ALLOWED_OPS = (
    "update_entity",
    "set_external_ref",
    "remove_external_ref",
    "set_entity_concept",
    "remove_entity_concept",
    "set_entity_tag",
    "remove_entity_tag",
)

REF_KINDS = {
    "wikidata": "wikidata",
    "imdb": "imdb_title",
    "tmdb": "tmdb_movie",
    "musicbrainz": "musicbrainz_release_group",
    "discogs": "discogs_release",
}

REF_VALUE_PATTERNS = {
    "wikidata": re.compile(r"^Q[1-9][0-9]*$"),
    "imdb": re.compile(r"^tt\d{6,10}$"),
    "tmdb": re.compile(r"^\d{1,12}$"),
    "musicbrainz": re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    "discogs": re.compile(r"^\d{1,12}$"),
}

UPDATE_ENTITY_FIELDS = {
    "label",
    "releaseDate",
    "datePrecision",
    "entityKind",
    "imageRef",
    "isCatalogued",
}

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

# Attachment download policy: explicit hostname and path allowlist.
ATTACHMENT_URL_HOSTS = {"github.com"}
ATTACHMENT_REDIRECT_HOSTS = {"objects.githubusercontent.com", "github-production-user-asset-6210df.s3.amazonaws.com"}
ATTACHMENT_PATH_RE = re.compile(r"^/user-attachments/files/\d+/[A-Za-z0-9._-]+\.(json|jsonl)$")


class BatchError(ValueError):
    """A batch failed parsing or validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class Operation:
    index: int
    op: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Batch:
    version: int
    operations: tuple[Operation, ...]


@dataclass
class ApplyResult:
    applied: dict[str, int] = field(default_factory=dict)
    noops: int = 0

    def record(self, op: str, changed: bool) -> None:
        if changed:
            self.applied[op] = self.applied.get(op, 0) + 1
        else:
            self.noops += 1

    def as_dict(self) -> dict[str, Any]:
        return {"applied": dict(sorted(self.applied.items())), "noops": self.noops}


# --------------------------------------------------------------------------
# Parsing


def parse_batch_text(text: str) -> Batch:
    """Parse a JSON or JSONL batch document. Raises BatchError."""
    if len(text.encode("utf-8")) > MAX_BATCH_BYTES:
        raise BatchError(["batch file exceeds the size limit"])

    stripped = text.strip()
    if not stripped:
        raise BatchError(["batch file is empty"])

    if stripped.startswith("{") and _is_single_json_document(stripped):
        return _batch_from_object(_load_json_object(stripped, "batch document"))
    return _batch_from_jsonl(stripped)


def _is_single_json_document(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def _load_json_object(text: str, what: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BatchError([f"invalid JSON in {what}: {exc.msg} (line {exc.lineno})"]) from exc
    if not isinstance(value, dict):
        raise BatchError([f"{what} must be a JSON object"])
    return value


def _batch_from_object(document: dict[str, Any]) -> Batch:
    errors: list[str] = []
    unknown = set(document) - {"version", "operations"}
    if unknown:
        errors.append(f"unknown top-level fields: {', '.join(sorted(unknown))}")

    version = document.get("version")
    if version != BATCH_VERSION:
        errors.append(f"unsupported batch version: {version!r} (expected {BATCH_VERSION})")

    raw_operations = document.get("operations")
    if not isinstance(raw_operations, list):
        errors.append("'operations' must be a list")
        raise BatchError(errors)
    if errors:
        raise BatchError(errors)
    return _batch_from_op_list(raw_operations)


def _batch_from_jsonl(text: str) -> Batch:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        rows.append(_load_json_object(line, f"JSONL line {line_number}"))

    if not rows:
        raise BatchError(["batch file contains no JSON objects"])

    if "version" in rows[0] and "op" not in rows[0]:
        header = rows.pop(0)
        unknown = set(header) - {"version"}
        if unknown:
            raise BatchError([f"unknown header fields: {', '.join(sorted(unknown))}"])
        if header.get("version") != BATCH_VERSION:
            raise BatchError([f"unsupported batch version: {header.get('version')!r}"])
    return _batch_from_op_list(rows)


def _batch_from_op_list(raw_operations: list[Any]) -> Batch:
    errors: list[str] = []
    if not raw_operations:
        errors.append("batch contains no operations")
    if len(raw_operations) > MAX_OPERATIONS:
        errors.append(f"too many operations: {len(raw_operations)} (limit {MAX_OPERATIONS})")
    if errors:
        raise BatchError(errors)

    operations: list[Operation] = []
    for index, raw in enumerate(raw_operations):
        if not isinstance(raw, dict):
            errors.append(f"operation {index}: must be a JSON object")
            continue
        op = raw.get("op")
        if op not in ALLOWED_OPS:
            errors.append(f"operation {index}: unknown op {op!r}")
            continue
        operations.append(Operation(index=index, op=str(op), payload=dict(raw)))

    if errors:
        raise BatchError(errors)
    return Batch(version=BATCH_VERSION, operations=tuple(operations))


# --------------------------------------------------------------------------
# Validation


def validate_batch(db: sqlite3.Connection, batch: Batch) -> None:
    """Validate all operations against the database. Raises BatchError."""
    errors: list[str] = []
    entity_field_targets: set[tuple[int, str]] = set()
    tag_targets: set[tuple[int, int]] = set()
    ref_targets: set[tuple[int, str]] = set()
    new_ref_values: dict[tuple[str, str], int] = {}

    for operation in batch.operations:
        prefix = f"operation {operation.index} ({operation.op})"
        payload = operation.payload

        entity_id = payload.get("entityId")
        if not isinstance(entity_id, int) or isinstance(entity_id, bool):
            errors.append(f"{prefix}: 'entityId' must be an integer")
            continue
        if not _entity_exists(db, entity_id):
            errors.append(f"{prefix}: entity {entity_id} does not exist")
            continue

        if operation.op == "update_entity":
            errors.extend(_validate_update_entity(prefix, payload, entity_field_targets, entity_id))
        elif operation.op in ("set_external_ref", "remove_external_ref"):
            errors.extend(
                _validate_external_ref(
                    db, prefix, operation.op, payload, entity_id, ref_targets, new_ref_values
                )
            )
        elif operation.op in ("set_entity_concept", "remove_entity_concept", "set_entity_tag", "remove_entity_tag"):
            errors.extend(
                _validate_entity_concept(db, prefix, operation.op, payload, entity_id, tag_targets)
            )

    if errors:
        raise BatchError(errors)


def _entity_exists(db: sqlite3.Connection, entity_id: int) -> bool:
    return db.execute("select 1 from entities where entity_id = ?", (entity_id,)).fetchone() is not None


def _concept_exists(db: sqlite3.Connection, concept_id: int) -> bool:
    return db.execute("select 1 from concepts where concept_id = ?", (concept_id,)).fetchone() is not None


def _identifier_scheme_id(db: sqlite3.Connection, kind: str) -> int:
    scheme = REF_KINDS[kind]
    row = db.execute(
        "select identifier_scheme_id from identifier_schemes where code = ?",
        (scheme,),
    ).fetchone()
    if row is None:
        raise BatchError([f"identifier scheme '{scheme}' is not configured"])
    return int(row[0])


def _validate_update_entity(
    prefix: str,
    payload: dict[str, Any],
    entity_field_targets: set[tuple[int, str]],
    entity_id: int,
) -> list[str]:
    errors: list[str] = []
    unknown = set(payload) - {"op", "entityId", "set"}
    if unknown:
        errors.append(f"{prefix}: unknown fields: {', '.join(sorted(unknown))}")

    updates = payload.get("set")
    if not isinstance(updates, dict) or not updates:
        errors.append(f"{prefix}: 'set' must be a non-empty object")
        return errors

    unknown_fields = set(updates) - UPDATE_ENTITY_FIELDS
    if unknown_fields:
        errors.append(f"{prefix}: unknown entity fields: {', '.join(sorted(unknown_fields))}")

    for field_name in updates:
        target = (entity_id, field_name)
        if target in entity_field_targets:
            errors.append(f"{prefix}: conflicting update for entity {entity_id} field '{field_name}'")
        entity_field_targets.add(target)

    label = updates.get("label")
    if "label" in updates and (not isinstance(label, str) or not label.strip() or len(label) > 500):
        errors.append(f"{prefix}: 'label' must be a non-empty string of at most 500 characters")

    if "releaseDate" in updates:
        release_date = updates["releaseDate"]
        if release_date is not None and not _valid_date(release_date):
            errors.append(f"{prefix}: 'releaseDate' must be null or a valid YYYY-MM-DD date")
        if release_date is not None and "datePrecision" not in updates:
            errors.append(f"{prefix}: setting 'releaseDate' requires an explicit 'datePrecision'")

    if "datePrecision" in updates:
        precision = updates["datePrecision"]
        if not isinstance(precision, int) or isinstance(precision, bool) or not 0 <= precision <= 3:
            errors.append(f"{prefix}: 'datePrecision' must be an integer from 0 to 3")
        elif updates.get("releaseDate") is None and "releaseDate" in updates and precision != 0:
            errors.append(f"{prefix}: 'datePrecision' must be 0 when 'releaseDate' is null")

    if "entityKind" in updates:
        kind = updates["entityKind"]
        if not isinstance(kind, int) or isinstance(kind, bool) or not 0 <= kind <= 255:
            errors.append(f"{prefix}: 'entityKind' must be an integer from 0 to 255")

    if "imageRef" in updates:
        image = updates["imageRef"]
        if image is not None and (not isinstance(image, str) or not image.strip() or len(image) > 500):
            errors.append(f"{prefix}: 'imageRef' must be null or a non-empty string")

    if "isCatalogued" in updates and not isinstance(updates["isCatalogued"], bool):
        errors.append(f"{prefix}: 'isCatalogued' must be a boolean")

    return errors


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = DATE_RE.match(value)
    if not match:
        return False
    year, month, day = (int(part) for part in match.groups())
    if year < 1 or not 1 <= month <= 12:
        return False
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return 1 <= day <= days_in_month


def _validate_external_ref(
    db: sqlite3.Connection,
    prefix: str,
    op: str,
    payload: dict[str, Any],
    entity_id: int,
    ref_targets: set[tuple[int, str]],
    new_ref_values: dict[tuple[str, str], int],
) -> list[str]:
    errors: list[str] = []
    unknown = set(payload) - {"op", "entityId", "kind", "value"}
    if unknown:
        errors.append(f"{prefix}: unknown fields: {', '.join(sorted(unknown))}")

    kind = payload.get("kind")
    if kind not in REF_KINDS:
        errors.append(f"{prefix}: 'kind' must be one of {', '.join(sorted(REF_KINDS))}")
        return errors

    value = payload.get("value")
    if not isinstance(value, str) or not REF_VALUE_PATTERNS[kind].match(value):
        errors.append(f"{prefix}: 'value' is not a valid {kind} reference")
        return errors
    try:
        scheme_id = _identifier_scheme_id(db, kind)
    except BatchError as exc:
        errors.extend(f"{prefix}: {message}" for message in exc.errors)
        return errors

    target = (entity_id, kind)
    if target in ref_targets:
        errors.append(f"{prefix}: conflicting operations on {kind} ref of entity {entity_id}")
    ref_targets.add(target)

    if op == "set_external_ref":
        row = db.execute(
            """
            select entity_id
            from entity_identifiers
            where identifier_scheme_id = ? and value = ?
            """,
            (scheme_id, value),
        ).fetchone()
        if row is not None and int(row[0]) != entity_id:
            errors.append(
                f"{prefix}: {kind} ref '{value}' already belongs to entity {int(row[0])}"
            )
        duplicate_owner = new_ref_values.get((kind, value))
        if duplicate_owner is not None and duplicate_owner != entity_id:
            errors.append(f"{prefix}: {kind} ref '{value}' is assigned twice in this batch")
        new_ref_values[(kind, value)] = entity_id

    return errors


def _validate_entity_concept(
    db: sqlite3.Connection,
    prefix: str,
    op: str,
    payload: dict[str, Any],
    entity_id: int,
    tag_targets: set[tuple[int, int]],
) -> list[str]:
    errors: list[str] = []
    is_set = op in ("set_entity_concept", "set_entity_tag")
    allowed = {"op", "entityId", "conceptId", "tagId", "weight", "polarity"} if is_set else {
        "op",
        "entityId",
        "conceptId",
        "tagId",
    }
    unknown = set(payload) - allowed
    if unknown:
        errors.append(f"{prefix}: unknown fields: {', '.join(sorted(unknown))}")

    concept_id = payload.get("conceptId", payload.get("tagId"))
    if not isinstance(concept_id, int) or isinstance(concept_id, bool):
        errors.append(f"{prefix}: 'conceptId' must be an integer")
        return errors
    if not _concept_exists(db, concept_id):
        errors.append(f"{prefix}: concept {concept_id} does not exist")
        return errors

    target = (entity_id, concept_id)
    if target in tag_targets:
        errors.append(f"{prefix}: conflicting operations on concept {concept_id} of entity {entity_id}")
    tag_targets.add(target)

    if is_set:
        weight = payload.get("weight")
        if weight is not None and (
            not isinstance(weight, int) or isinstance(weight, bool) or not 0 <= weight <= 100
        ):
            errors.append(f"{prefix}: 'weight' must be null or an integer from 0 to 100")
        polarity = payload.get("polarity", 0)
        if polarity not in (-1, 0, 1) or isinstance(polarity, bool):
            errors.append(f"{prefix}: 'polarity' must be -1, 0, or 1")

    return errors


# --------------------------------------------------------------------------
# Application


def apply_batch(db: sqlite3.Connection, batch: Batch) -> ApplyResult:
    """Apply a validated batch. Idempotent: reapplying changes nothing."""
    result = ApplyResult()
    for operation in batch.operations:
        payload = operation.payload
        entity_id = int(payload["entityId"])
        if operation.op == "update_entity":
            result.record(operation.op, _apply_update_entity(db, entity_id, payload["set"]))
        elif operation.op == "set_external_ref":
            result.record(operation.op, _apply_set_ref(db, entity_id, payload["kind"], payload["value"]))
        elif operation.op == "remove_external_ref":
            result.record(operation.op, _apply_remove_ref(db, entity_id, payload["kind"], payload["value"]))
        elif operation.op in ("set_entity_concept", "set_entity_tag"):
            concept_id = int(payload.get("conceptId", payload.get("tagId")))
            result.record(
                operation.op,
                _apply_set_concept(db, entity_id, concept_id, payload.get("weight"), int(payload.get("polarity", 0))),
            )
        elif operation.op in ("remove_entity_concept", "remove_entity_tag"):
            concept_id = int(payload.get("conceptId", payload.get("tagId")))
            result.record(operation.op, _apply_remove_concept(db, entity_id, concept_id))
    return result


COLUMN_BY_FIELD = {
    "label": "label",
    "releaseDate": "release_date",
    "datePrecision": "date_precision",
    "entityKind": "entity_kind",
    "imageRef": "image_ref",
    "isCatalogued": "is_catalogued",
}


def _apply_update_entity(db: sqlite3.Connection, entity_id: int, updates: dict[str, Any]) -> bool:
    row = db.execute(
        "select label, release_date, date_precision, entity_kind, image_ref, is_catalogued "
        "from entities where entity_id = ?",
        (entity_id,),
    ).fetchone()
    assignments: list[str] = []
    values: list[Any] = []
    for field_name, raw_value in updates.items():
        column = COLUMN_BY_FIELD[field_name]
        value: Any = raw_value
        if field_name == "isCatalogued":
            value = 1 if raw_value else 0
        if row[column] != value:
            assignments.append(f"{column} = ?")
            values.append(value)
    if not assignments:
        return False
    values.append(entity_id)
    db.execute(f"update entities set {', '.join(assignments)} where entity_id = ?", values)
    return True


def _apply_set_ref(db: sqlite3.Connection, entity_id: int, kind: str, value: str) -> bool:
    scheme_id = _identifier_scheme_id(db, kind)
    row = db.execute(
        """
        select value
        from entity_identifiers
        where entity_id = ? and identifier_scheme_id = ?
        """,
        (entity_id, scheme_id),
    ).fetchone()
    if row is not None and row[0] == value:
        return False
    if row is None:
        db.execute(
            """
            insert into entity_identifiers(entity_id, identifier_scheme_id, value, is_primary)
            values (?, ?, ?, 1)
            """,
            (entity_id, scheme_id, value),
        )
    else:
        db.execute(
            """
            update entity_identifiers
            set value = ?
            where entity_id = ? and identifier_scheme_id = ?
            """,
            (value, entity_id, scheme_id),
        )
    return True


def _apply_remove_ref(db: sqlite3.Connection, entity_id: int, kind: str, value: str) -> bool:
    scheme_id = _identifier_scheme_id(db, kind)
    cursor = db.execute(
        """
        delete from entity_identifiers
        where entity_id = ? and identifier_scheme_id = ? and value = ?
        """,
        (entity_id, scheme_id, value),
    )
    return cursor.rowcount > 0


def _apply_set_concept(
    db: sqlite3.Connection,
    entity_id: int,
    concept_id: int,
    weight: int | None,
    polarity: int,
) -> bool:
    row = db.execute(
        "select weight, polarity from entity_concepts where entity_id = ? and concept_id = ?",
        (entity_id, concept_id),
    ).fetchone()
    if row is not None and row[0] == weight and int(row[1]) == polarity:
        return False
    db.execute(
        """
        insert into entity_concepts(entity_id, concept_id, weight, polarity)
        values (?, ?, ?, ?)
        on conflict(entity_id, concept_id) do update set weight = excluded.weight, polarity = excluded.polarity
        """,
        (entity_id, concept_id, weight, polarity),
    )
    return True


def _apply_remove_concept(db: sqlite3.Connection, entity_id: int, concept_id: int) -> bool:
    cursor = db.execute(
        "delete from entity_concepts where entity_id = ? and concept_id = ?",
        (entity_id, concept_id),
    )
    return cursor.rowcount > 0


# --------------------------------------------------------------------------
# Issue-body extraction and safe attachment download

FENCE_RE = re.compile(r"```(?:json[l]?)?\s*\n(.*?)```", re.DOTALL)
URL_RE = re.compile(r"https://[^\s)\]>\"']+")


@dataclass(frozen=True)
class BatchSource:
    kind: str  # "inline" | "url"
    text: str | None = None
    url: str | None = None


def extract_batch_source(issue_body: str) -> BatchSource:
    """Find exactly one fenced JSON batch or one allowlisted attachment URL."""
    fenced = [block.strip() for block in FENCE_RE.findall(issue_body or "") if block.strip()]
    fenced = [block for block in fenced if block.startswith("{") or block.startswith("[")]
    urls = [url for url in URL_RE.findall(issue_body or "") if is_allowed_attachment_url(url)]

    if len(fenced) + len(urls) == 0:
        raise BatchError(
            [
                "no batch found: attach one .json/.jsonl file uploaded to GitHub "
                "or include one fenced ```json block"
            ]
        )
    if len(fenced) + len(urls) > 1:
        raise BatchError(["found more than one batch candidate; submit exactly one"])

    if fenced:
        return BatchSource(kind="inline", text=fenced[0])
    return BatchSource(kind="url", url=urls[0])


def is_allowed_attachment_url(url: str) -> bool:
    """Explicit hostname and path allowlist for GitHub user attachments."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.hostname not in ATTACHMENT_URL_HOSTS:
        return False
    return ATTACHMENT_PATH_RE.match(parsed.path) is not None


def is_allowed_redirect_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in ATTACHMENT_REDIRECT_HOSTS


def decode_batch_bytes(data: bytes) -> str:
    """Enforce the size limit, reject binary data, and validate UTF-8."""
    if len(data) > MAX_BATCH_BYTES:
        raise BatchError(["attachment exceeds the size limit"])
    if b"\x00" in data:
        raise BatchError(["attachment contains binary data"])
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BatchError(["attachment is not valid UTF-8"]) from exc
    control = [ch for ch in text if unicodedata.category(ch) == "Cc" and ch not in "\r\n\t"]
    if control:
        raise BatchError(["attachment contains control characters"])
    return text


def download_attachment(
    url: str,
    opener: Callable[[str], tuple[int, str | None, bytes]] | None = None,
    max_redirects: int = 3,
) -> str:
    """Download an allowlisted attachment, following redirects only to
    allowlisted hosts, never executing content, and enforcing limits.

    ``opener`` performs one non-redirecting HTTP GET and returns
    ``(status, location_header, body)``. It is injectable for tests.
    """
    if not is_allowed_attachment_url(url):
        raise BatchError([f"attachment URL is not an allowed GitHub user-attachment: {url}"])

    fetch = opener or _default_opener
    current = url
    for _ in range(max_redirects + 1):
        status, location, body = fetch(current)
        if status in (301, 302, 303, 307, 308):
            if not location:
                raise BatchError(["redirect without a Location header"])
            if not (is_allowed_attachment_url(location) or is_allowed_redirect_url(location)):
                raise BatchError([f"redirect to a non-allowlisted host rejected: {location}"])
            current = location
            continue
        if status != 200:
            raise BatchError([f"attachment download failed with HTTP {status}"])
        return decode_batch_bytes(body)
    raise BatchError(["too many redirects while downloading the attachment"])


def _default_opener(url: str) -> tuple[int, str | None, bytes]:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "art-islands-batch/1"})
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read(MAX_BATCH_BYTES + 1)
            return response.status, response.headers.get("Location"), body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location"), b""
