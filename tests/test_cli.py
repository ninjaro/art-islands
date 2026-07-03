from __future__ import annotations

from types import SimpleNamespace

import pytest

from art_islands import cli
from art_islands.model import connect_art


def test_cli_parser_rejects_invalid_fields_and_tag_values() -> None:
    parser = cli.parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["enrich", "--all-missing", "--fields", "label,bogus"])

    with pytest.raises(SystemExit):
        parser.parse_args(["tag", "set", "--entity", "1", "--tag", "2", "--weight", "101"])

    with pytest.raises(SystemExit):
        parser.parse_args(["tag", "set", "--entity", "1", "--tag", "2", "--polarity", "2"])


def test_tag_set_updates_existing_entity_tag(tmp_path) -> None:
    db_path = tmp_path / "art.sqlite"
    db = connect_art(db_path)
    try:
        db.execute(
            """
            insert into entities(entity_id, label, entity_kind, is_catalogued)
            values (1, 'Work', 7, 1)
            """
        )
        db.execute("insert into tags(tag_id, name) values (10, 'dream_logic')")
        db.execute(
            """
            insert into entity_tags(entity_id, tag_id, weight, polarity)
            values (1, 10, 50, 0)
            """
        )
        db.commit()
    finally:
        db.close()

    cli.command_tag_set(
        SimpleNamespace(db=db_path, entity=1, tag=10, weight=90, polarity=-1)
    )

    db = connect_art(db_path)
    try:
        row = db.execute(
            "select weight, polarity from entity_tags where entity_id = 1 and tag_id = 10"
        ).fetchone()
        assert dict(row) == {"weight": 90, "polarity": -1}
    finally:
        db.close()


def test_tag_set_rejects_missing_entity_tag_row(tmp_path) -> None:
    db_path = tmp_path / "art.sqlite"
    db = connect_art(db_path)
    try:
        db.execute(
            """
            insert into entities(entity_id, label, entity_kind, is_catalogued)
            values (1, 'Work', 7, 1)
            """
        )
        db.execute("insert into tags(tag_id, name) values (10, 'dream_logic')")
        db.commit()
    finally:
        db.close()

    with pytest.raises(SystemExit, match="entity_tags row does not exist"):
        cli.command_tag_set(
            SimpleNamespace(db=db_path, entity=1, tag=10, weight=75, polarity=None)
        )


def test_config_set_rejects_invalid_values(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"

    with pytest.raises(SystemExit, match="non-negative"):
        cli.command_config_set(
            SimpleNamespace(
                settings=settings_path,
                key="recommendation.like-weight",
                value="-1",
            )
        )

    with pytest.raises(SystemExit, match="positive integer"):
        cli.command_config_set(
            SimpleNamespace(
                settings=settings_path,
                key="recommendation.limit",
                value="0",
            )
        )
