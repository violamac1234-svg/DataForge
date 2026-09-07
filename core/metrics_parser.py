from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd


METRIC_ALIASES = {
    "epoch": ("epoch",),
    "box_loss": ("train/box_loss", "box_loss"),
    "cls_loss": ("train/cls_loss", "cls_loss"),
    "precision": ("metrics/precision(B)", "metrics/precision", "precision"),
    "recall": ("metrics/recall(B)", "metrics/recall", "recall"),
    "map50": ("metrics/mAP50(B)", "metrics/mAP50", "map50"),
    "map5095": ("metrics/mAP50-95(B)", "metrics/mAP50-95", "map5095"),
}


def _finite(value: Any) -> float | int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def parse_metrics(results_csv: str | Path) -> list[dict[str, float | int | None]]:
    """Normalize changing Ultralytics CSV column names for the UI."""
    path = Path(results_csv)
    if not path.is_file() or path.stat().st_size == 0:
        return []
    try:
        frame = pd.read_csv(path)
    except Exception:
        return []
    frame.columns = [str(column).strip() for column in frame.columns]
    rows = []
    for row_index, source in frame.iterrows():
        target: dict[str, float | int | None] = {}
        for key, aliases in METRIC_ALIASES.items():
            value = None
            for alias in aliases:
                if alias in frame.columns:
                    value = _finite(source[alias])
                    break
            target[key] = value
        if target["epoch"] is None:
            target["epoch"] = row_index + 1
        else:
            target["epoch"] = int(target["epoch"]) + 1
        rows.append(target)
    return rows


def latest_metrics(results_csv: str | Path) -> dict[str, float | int | None] | None:
    rows = parse_metrics(results_csv)
    return rows[-1] if rows else None
