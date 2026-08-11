import pytest

from clauseguard.json_utils import parse_json_object


def test_parse_json_object_accepts_fenced_json():
    parsed = parse_json_object('```json\n{"status": "ok"}\n```')

    assert parsed == {"status": "ok"}


def test_parse_json_object_extracts_object_from_surrounding_text():
    parsed = parse_json_object('Result follows: {"findings": []} End.')

    assert parsed == {"findings": []}


def test_parse_json_object_rejects_array():
    with pytest.raises(ValueError, match="Expected a JSON object"):
        parse_json_object("[]")
