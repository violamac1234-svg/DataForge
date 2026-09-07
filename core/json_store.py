from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonStoreError(RuntimeError):
    """Raised when a JSON document cannot be read or safely written."""


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read UTF-8 JSON, returning *default* for missing or empty files."""
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return default
    try:
        with target.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise JsonStoreError(f"无法读取 JSON：{target.name}") from exc


def write_json_atomic(path: str | Path, data: Any) -> None:
    """Write UTF-8 JSON through a same-directory temporary file and replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            temp_path = Path(stream.name)
        os.replace(temp_path, target)
    except (OSError, TypeError, ValueError) as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise JsonStoreError(f"无法写入 JSON：{target.name}") from exc
