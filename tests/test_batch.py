from __future__ import annotations

import json

import pytest

from art_islands import batch
from art_islands.model import connect_art


@pytest.fixture()
def db(tmp_path):
    connection = connect_art(tmp_path / "art.sqlite")
    connection.executemany(
        """
        insert into entities(entity_id, label, entity_kind, release_date, date_precision, is_catalogued)
        values (?, ?, ?, ?, ?, ?)
        """,
        [
            (123, "Original title", 1, "1980-05-01", 3, 1),
            (200, "Other work", 2, None, 0, 1),
        ],
    )
    connection.executemany(
        "insert into tags(tag_id, name) values (?, ?)",
        [(456, "alpha"), (789, "beta")],
    )
    connection.execute(
        "insert into entity_tags(entity_id, tag_id, weight, polarity) values (123, 789, 40, 0)"
    )
    connection.execute(
        "insert into entity_refs(entity_id, ref_kind, ref_value) values (200, 2, 'tt0000001')"
    )
    connection.commit()
    yield connection
    connection.close()


def valid_batch() -> dict:
    return {
        "version": 1,
        "operations": [
            {
                "op": "update_entity",
                "entityId": 123,
                "set": {
                    "label": "Corrected title",
                    "releaseDate": "1981-01-01",
                    "datePrecision": 1,
                    "entityKind": 2,
                    "imageRef": None,
                    "isCatalogued": True,
                },
            },
            {"op": "set_external_ref", "entityId": 123, "kind": "wikidata", "value": "Q12345"},
            {"op": "remove_external_ref", "entityId": 200, "kind": "imdb", "value": "tt0000001"},
            {"op": "set_entity_tag", "entityId": 123, "tagId": 456, "weight": 75, "polarity": 0},
            {"op": "remove_entity_tag", "entityId": 123, "tagId": 789},
        ],
    }


class TestParsing:
    def test_parses_json_document(self) -> None:
        parsed = batch.parse_batch_text(json.dumps(valid_batch()))
        assert parsed.version == 1
        assert len(parsed.operations) == 5

    def test_parses_jsonl_with_header(self) -> None:
        lines = [json.dumps({"version": 1})] + [
            json.dumps(operation) for operation in valid_batch()["operations"]
        ]
        parsed = batch.parse_batch_text("\n".join(lines))
        assert len(parsed.operations) == 5

    def test_rejects_wrong_version(self) -> None:
        document = valid_batch()
        document["version"] = 2
        with pytest.raises(batch.BatchError, match="version"):
            batch.parse_batch_text(json.dumps(document))

    def test_rejects_unknown_operation(self) -> None:
        document = {"version": 1, "operations": [{"op": "run_sql", "sql": "drop table entities"}]}
        with pytest.raises(batch.BatchError, match="unknown op"):
            batch.parse_batch_text(json.dumps(document))

    def test_rejects_unknown_top_level_fields(self) -> None:
        document = valid_batch()
        document["script"] = "echo hi"
        with pytest.raises(batch.BatchError, match="unknown top-level"):
            batch.parse_batch_text(json.dumps(document))

    def test_rejects_empty_and_oversized(self) -> None:
        with pytest.raises(batch.BatchError):
            batch.parse_batch_text("")
        document = {"version": 1, "operations": [{"op": "remove_entity_tag", "entityId": 1, "tagId": 2}] * 1001}
        with pytest.raises(batch.BatchError, match="too many operations"):
            batch.parse_batch_text(json.dumps(document))


class TestValidation:
    def test_valid_batch_passes(self, db) -> None:
        parsed = batch.parse_batch_text(json.dumps(valid_batch()))
        batch.validate_batch(db, parsed)

    def test_missing_entity_and_tag(self, db) -> None:
        document = {
            "version": 1,
            "operations": [
                {"op": "update_entity", "entityId": 999, "set": {"label": "X"}},
                {"op": "set_entity_tag", "entityId": 123, "tagId": 999, "weight": 10},
            ],
        }
        with pytest.raises(batch.BatchError) as info:
            batch.validate_batch(db, batch.parse_batch_text(json.dumps(document)))
        assert any("entity 999 does not exist" in message for message in info.value.errors)
        assert any("tag 999 does not exist" in message for message in info.value.errors)

    @pytest.mark.parametrize(
        "updates,match",
        [
            ({"label": ""}, "label"),
            ({"releaseDate": "1981-13-01", "datePrecision": 1}, "releaseDate"),
            ({"releaseDate": "1981-02-30", "datePrecision": 1}, "releaseDate"),
            ({"releaseDate": "1981-01-01"}, "datePrecision"),
            ({"datePrecision": 9}, "datePrecision"),
            ({"entityKind": 300}, "entityKind"),
            ({"isCatalogued": "yes"}, "isCatalogued"),
            ({"unknownField": 1}, "unknown entity fields"),
        ],
    )
    def test_rejects_bad_entity_updates(self, db, updates, match) -> None:
        document = {"version": 1, "operations": [{"op": "update_entity", "entityId": 123, "set": updates}]}
        with pytest.raises(batch.BatchError, match=match):
            batch.validate_batch(db, batch.parse_batch_text(json.dumps(document)))

    @pytest.mark.parametrize(
        "operation,match",
        [
            ({"op": "set_entity_tag", "entityId": 123, "tagId": 456, "weight": 101}, "weight"),
            ({"op": "set_entity_tag", "entityId": 123, "tagId": 456, "weight": 10, "polarity": 5}, "polarity"),
            ({"op": "set_external_ref", "entityId": 123, "kind": "unknown", "value": "x"}, "kind"),
            ({"op": "set_external_ref", "entityId": 123, "kind": "wikidata", "value": "12345"}, "value"),
            ({"op": "set_external_ref", "entityId": 123, "kind": "imdb", "value": "tt0000001"}, "already belongs"),
        ],
    )
    def test_rejects_bad_values(self, db, operation, match) -> None:
        document = {"version": 1, "operations": [operation]}
        with pytest.raises(batch.BatchError, match=match):
            batch.validate_batch(db, batch.parse_batch_text(json.dumps(document)))

    def test_rejects_conflicting_operations(self, db) -> None:
        document = {
            "version": 1,
            "operations": [
                {"op": "set_entity_tag", "entityId": 123, "tagId": 456, "weight": 10},
                {"op": "remove_entity_tag", "entityId": 123, "tagId": 456},
            ],
        }
        with pytest.raises(batch.BatchError, match="conflicting"):
            batch.validate_batch(db, batch.parse_batch_text(json.dumps(document)))

    def test_rejects_duplicate_ref_assignment_in_batch(self, db) -> None:
        document = {
            "version": 1,
            "operations": [
                {"op": "set_external_ref", "entityId": 123, "kind": "wikidata", "value": "Q7"},
                {"op": "set_external_ref", "entityId": 200, "kind": "wikidata", "value": "Q7"},
            ],
        }
        with pytest.raises(batch.BatchError, match="assigned twice"):
            batch.validate_batch(db, batch.parse_batch_text(json.dumps(document)))


class TestApplication:
    def test_applies_and_is_idempotent(self, db) -> None:
        parsed = batch.parse_batch_text(json.dumps(valid_batch()))
        batch.validate_batch(db, parsed)
        first = batch.apply_batch(db, parsed)
        db.commit()

        row = db.execute("select * from entities where entity_id = 123").fetchone()
        assert row["label"] == "Corrected title"
        assert row["release_date"] == "1981-01-01"
        assert row["date_precision"] == 1
        assert row["entity_kind"] == 2
        assert row["image_ref"] is None
        assert row["is_catalogued"] == 1

        wikidata = db.execute(
            "select ref_value from entity_refs where entity_id = 123 and ref_kind = 1"
        ).fetchone()
        assert wikidata[0] == "Q12345"
        assert db.execute("select count(*) from entity_refs where ref_kind = 2").fetchone()[0] == 0

        tag = db.execute(
            "select weight, polarity from entity_tags where entity_id = 123 and tag_id = 456"
        ).fetchone()
        assert (tag[0], tag[1]) == (75, 0)
        assert (
            db.execute("select count(*) from entity_tags where entity_id = 123 and tag_id = 789").fetchone()[0]
            == 0
        )
        assert sum(first.applied.values()) == 5

        # Second application must be a pure no-op.
        batch.validate_batch(db, parsed)
        second = batch.apply_batch(db, parsed)
        assert second.applied == {}
        assert second.noops == 5
        assert db.execute("pragma foreign_key_check").fetchall() == []

    def test_foreign_keys_stay_valid(self, db) -> None:
        parsed = batch.parse_batch_text(json.dumps(valid_batch()))
        batch.validate_batch(db, parsed)
        batch.apply_batch(db, parsed)
        db.commit()
        assert db.execute("pragma foreign_key_check").fetchall() == []


class TestIssueExtraction:
    def test_extracts_single_fenced_block(self) -> None:
        body = "Fix data\n\n```json\n" + json.dumps(valid_batch()) + "\n```\nthanks"
        source = batch.extract_batch_source(body)
        assert source.kind == "inline"
        assert json.loads(source.text or "")["version"] == 1

    def test_extracts_single_attachment_url(self) -> None:
        url = "https://github.com/user-attachments/files/12345/fix.json"
        source = batch.extract_batch_source(f"Batch attached: {url}")
        assert source.kind == "url"
        assert source.url == url

    def test_rejects_zero_or_multiple_candidates(self) -> None:
        with pytest.raises(batch.BatchError, match="no batch found"):
            batch.extract_batch_source("just words")
        body = (
            "```json\n{}\n```\nhttps://github.com/user-attachments/files/1/a.json"
        )
        with pytest.raises(batch.BatchError, match="more than one"):
            batch.extract_batch_source(body)

    @pytest.mark.parametrize(
        "url,allowed",
        [
            ("https://github.com/user-attachments/files/1/fix.json", True),
            ("https://github.com/user-attachments/files/1/fix.jsonl", True),
            ("https://github.com/user-attachments/files/1/fix.exe", False),
            ("https://github.com/user-attachments/files/1/fix.bat", False),
            ("https://github.com/user-attachments/files/1/fix.sql", False),
            ("https://github.com/other/path/fix.json", False),
            ("https://evil.example.com/user-attachments/files/1/fix.json", False),
            ("http://github.com/user-attachments/files/1/fix.json", False),
            ("https://github.com/user-attachments/files/1/../fix.json", False),
        ],
    )
    def test_attachment_allowlist(self, url, allowed) -> None:
        assert batch.is_allowed_attachment_url(url) is allowed


class TestDownload:
    def test_rejects_redirect_to_other_host(self) -> None:
        def opener(url):
            return 302, "https://evil.example.com/x.json", b""

        with pytest.raises(batch.BatchError, match="non-allowlisted host"):
            batch.download_attachment(
                "https://github.com/user-attachments/files/1/fix.json", opener=opener
            )

    def test_follows_allowed_redirect_and_decodes(self) -> None:
        payload = json.dumps(valid_batch()).encode("utf-8")

        def opener(url):
            if url.startswith("https://github.com/"):
                return 302, "https://objects.githubusercontent.com/abc", b""
            return 200, None, payload

        text = batch.download_attachment(
            "https://github.com/user-attachments/files/1/fix.json", opener=opener
        )
        assert json.loads(text)["version"] == 1

    def test_rejects_binary_and_invalid_utf8(self) -> None:
        with pytest.raises(batch.BatchError, match="binary"):
            batch.decode_batch_bytes(b"\x00\x01\x02")
        with pytest.raises(batch.BatchError, match="UTF-8"):
            batch.decode_batch_bytes(b"\xff\xfe{}")

    def test_rejects_oversized_body(self) -> None:
        with pytest.raises(batch.BatchError, match="size limit"):
            batch.decode_batch_bytes(b"x" * (batch.MAX_BATCH_BYTES + 1))
