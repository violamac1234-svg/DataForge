import json

import pytest

from core.json_store import JsonStoreError, read_json, write_json_atomic


def test_atomic_write_and_unicode(tmp_path):
    target = tmp_path / "data.json"
    write_json_atomic(target, {"name": "炼数", "value": 3})
    assert read_json(target) == {"name": "炼数", "value": 3}
    assert "炼数" in target.read_text(encoding="utf-8")
    assert list(tmp_path.glob("*.tmp")) == []


def test_empty_file_returns_default(tmp_path):
    target = tmp_path / "empty.json"
    target.touch()
    assert read_json(target, {"ok": True}) == {"ok": True}


def test_broken_json_raises(tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{broken", encoding="utf-8")
    with pytest.raises(JsonStoreError):
        read_json(target)
