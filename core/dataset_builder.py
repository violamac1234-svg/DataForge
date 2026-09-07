from __future__ import annotations

import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from config import DATASET_SEED, DEFAULT_TRAIN_RATIO
from core.annotation_manager import load_annotation, validate_annotation, xyxy_to_yolo
from core.image_manager import image_file_path, list_images
from core.json_store import write_json_atomic
from core.project_manager import get_project_dir, load_project, now_iso


class DatasetError(ValueError):
    """Raised when verified project data cannot form a valid YOLO dataset."""


def _verified_records(project_id: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    records = []
    for image in list_images(project_id, sort_by="oldest"):
        if image["status"] != "verified":
            continue
        source = image_file_path(project_id, image["id"])
        if not source.is_file():
            raise DatasetError(f"图片文件缺失：{image['filename']}")
        try:
            annotation = load_annotation(project_id, image["id"])
            validate_annotation(project_id, annotation, expected_image_id=image["id"])
        except Exception as exc:
            raise DatasetError(f"标注非法：{image['filename']}。{exc}") from exc
        records.append((image, annotation))
    if not records:
        raise DatasetError("没有 Verified 图片，无法构建训练数据集。")
    if sum(len(annotation["objects"]) for _, annotation in records) == 0:
        raise DatasetError("Verified 数据全部为负样本，没有任何正样本。")
    return records


def _split_ids(image_ids: list[str], train_ratio: float, seed: int) -> tuple[list[str], list[str]]:
    if not 0 < train_ratio < 1:
        raise DatasetError("Train Ratio 必须在 0 和 1 之间。")
    shuffled = list(image_ids)
    random.Random(seed).shuffle(shuffled)
    if len(shuffled) == 1:
        return shuffled, []
    train_count = max(1, min(len(shuffled) - 1, int(len(shuffled) * train_ratio)))
    return shuffled[:train_count], shuffled[train_count:]


def build_dataset(
    project_id: str,
    job_id: str,
    *,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    seed: int = DATASET_SEED,
) -> Path:
    """Freeze valid Verified data into an independent YOLO dataset snapshot."""
    project = load_project(project_id)
    records = _verified_records(project_id)
    by_id = {image["id"]: (image, annotation) for image, annotation in records}
    train_ids, val_ids = _split_ids(list(by_id), train_ratio, seed)
    snapshot = get_project_dir(project_id) / "datasets" / job_id
    if snapshot.exists():
        raise DatasetError("同名 Dataset Snapshot 已存在。")

    try:
        for split in ("train", "val"):
            (snapshot / "images" / split).mkdir(parents=True, exist_ok=False)
            (snapshot / "labels" / split).mkdir(parents=True, exist_ok=False)

        class_counts: Counter[int] = Counter()
        negative_images = 0
        for split, image_ids in (("train", train_ids), ("val", val_ids)):
            for image_id in image_ids:
                image, annotation = by_id[image_id]
                source = image_file_path(project_id, image_id)
                shutil.copy2(source, snapshot / "images" / split / image["stored_name"])
                label_lines = []
                for obj in annotation["objects"]:
                    class_counts[obj["class_id"]] += 1
                    x, y, width, height = xyxy_to_yolo(obj["bbox"])
                    label_lines.append(f"{obj['class_id']} {x:.8f} {y:.8f} {width:.8f} {height:.8f}")
                if not label_lines:
                    negative_images += 1
                (snapshot / "labels" / split / f"{Path(image['stored_name']).stem}.txt").write_text(
                    "\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8"
                )

        data_yaml = {
            "path": str(snapshot.resolve()),
            "train": "images/train",
            "val": "images/val",
            "names": {item["id"]: item["name"] for item in project["classes"]},
        }
        with (snapshot / "data.yaml").open("w", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(data_yaml, stream, allow_unicode=True, sort_keys=False)
        manifest = {
            "schema_version": 1,
            "job_id": job_id,
            "created_at": now_iso(),
            "train_ratio": train_ratio,
            "seed": seed,
            "train_images": train_ids,
            "val_images": val_ids,
            "class_counts": {str(item["id"]): class_counts[item["id"]] for item in project["classes"]},
            "negative_images": negative_images,
        }
        write_json_atomic(snapshot / "manifest.json", manifest)
        return snapshot
    except Exception:
        if snapshot.exists():
            shutil.rmtree(snapshot)
        raise


def dataset_summary(project_id: str) -> dict[str, Any]:
    project = load_project(project_id)
    images = [item for item in list_images(project_id) if item["status"] == "verified"]
    counts: Counter[int] = Counter()
    negatives = 0
    invalid: list[str] = []
    for image in images:
        try:
            annotation = load_annotation(project_id, image["id"])
            validate_annotation(project_id, annotation, expected_image_id=image["id"])
            if not annotation["objects"]:
                negatives += 1
            counts.update(obj["class_id"] for obj in annotation["objects"])
        except Exception as exc:
            invalid.append(f"{image['filename']}: {exc}")
    return {
        "verified_images": len(images),
        "object_count": sum(counts.values()),
        "negative_images": negatives,
        "class_counts": {str(item["id"]): counts[item["id"]] for item in project["classes"]},
        "invalid": invalid,
    }
