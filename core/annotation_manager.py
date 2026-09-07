from __future__ import annotations

import math
import secrets
from pathlib import Path
from typing import Any

from core.image_manager import get_image, set_image_status, update_annotation_count
from core.json_store import read_json, write_json_atomic
from core.project_manager import get_project_dir, load_project, now_iso


class AnnotationError(ValueError):
    """Raised when annotation data violates the frozen schema."""


def annotation_path(project_id: str, image_id: str) -> Path:
    get_image(project_id, image_id)
    return get_project_dir(project_id) / "annotations" / f"{image_id}.json"


def empty_annotation(project_id: str, image_id: str) -> dict[str, Any]:
    image = get_image(project_id, image_id)
    return {
        "schema_version": 1,
        "image_id": image_id,
        "image_width": image["width"],
        "image_height": image["height"],
        "objects": [],
        "updated_at": now_iso(),
    }


def load_annotation(project_id: str, image_id: str) -> dict[str, Any]:
    path = annotation_path(project_id, image_id)
    data = read_json(path)
    if data is None:
        return empty_annotation(project_id, image_id)
    validate_annotation(project_id, data, expected_image_id=image_id)
    return data


def validate_bbox(bbox: Any) -> list[float]:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise AnnotationError("BBox 必须是包含四个数值的 XYXY 数组。")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox):
        raise AnnotationError("BBox 坐标必须是数值。")
    values = [float(value) for value in bbox]
    if not all(math.isfinite(value) for value in values):
        raise AnnotationError("BBox 坐标必须是有限数值。")
    x1, y1, x2, y2 = values
    if not all(0.0 <= value <= 1.0 for value in values):
        raise AnnotationError("BBox 坐标必须在 0 到 1 之间。")
    if x1 >= x2 or y1 >= y2:
        raise AnnotationError("BBox 必须满足 x1 < x2 且 y1 < y2。")
    return values


def xyxy_to_yolo(bbox: Any) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = validate_bbox(bbox)
    return ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)


def validate_annotation(
    project_id: str,
    data: Any,
    *,
    expected_image_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise AnnotationError("标注文件结构或 schema_version 非法。")
    image_id = data.get("image_id")
    if not isinstance(image_id, str) or (expected_image_id and image_id != expected_image_id):
        raise AnnotationError("标注所属图片不匹配。")
    image = get_image(project_id, image_id)
    if data.get("image_width") != image["width"] or data.get("image_height") != image["height"]:
        raise AnnotationError("标注中的图片尺寸与原图不一致。")
    objects = data.get("objects")
    if not isinstance(objects, list):
        raise AnnotationError("objects 必须是数组。")
    class_ids = {item["id"] for item in load_project(project_id)["classes"]}
    seen_ids: set[str] = set()
    for index, obj in enumerate(objects, start=1):
        if not isinstance(obj, dict):
            raise AnnotationError(f"第 {index} 个目标结构非法。")
        object_id = obj.get("id")
        if not isinstance(object_id, str) or not object_id.startswith("obj_") or object_id in seen_ids:
            raise AnnotationError(f"第 {index} 个目标 ID 非法或重复。")
        seen_ids.add(object_id)
        if obj.get("class_id") not in class_ids:
            raise AnnotationError(f"第 {index} 个目标的 class_id 不存在。")
        validate_bbox(obj.get("bbox"))
        origin = obj.get("origin")
        if origin not in {"manual", "ai"}:
            raise AnnotationError(f"第 {index} 个目标的 origin 非法。")
        confidence = obj.get("confidence")
        if origin == "manual" and confidence is not None:
            raise AnnotationError("人工目标的 confidence 必须为 null。")
        if origin == "ai" and confidence is not None:
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise AnnotationError("AI 目标的 confidence 必须为 0 到 1 或 null。")
        if not isinstance(obj.get("edited"), bool):
            raise AnnotationError(f"第 {index} 个目标的 edited 必须是布尔值。")
    return data


def normalize_annotation(project_id: str, image_id: str, data: dict[str, Any]) -> dict[str, Any]:
    image = get_image(project_id, image_id)
    normalized_objects = []
    for obj in data.get("objects", []):
        item = dict(obj)
        item.setdefault("id", f"obj_{secrets.token_hex(4)}")
        item["bbox"] = [round(value, 8) for value in validate_bbox(item.get("bbox"))]
        item.setdefault("origin", "manual")
        item.setdefault("confidence", None)
        item.setdefault("edited", False)
        normalized_objects.append(item)
    normalized = {
        "schema_version": 1,
        "image_id": image_id,
        "image_width": image["width"],
        "image_height": image["height"],
        "objects": normalized_objects,
        "updated_at": now_iso(),
    }
    validate_annotation(project_id, normalized, expected_image_id=image_id)
    return normalized


def save_annotation(project_id: str, image_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Save a draft without changing the image business status."""
    normalized = normalize_annotation(project_id, image_id, data)
    write_json_atomic(annotation_path(project_id, image_id), normalized)
    update_annotation_count(project_id, image_id, len(normalized["objects"]))
    return normalized


def verify_image(project_id: str, image_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Persist valid annotation data, including valid zero-target samples, then verify."""
    normalized = save_annotation(project_id, image_id, data)
    set_image_status(project_id, image_id, "verified")
    return normalized


def delete_annotation(project_id: str, image_id: str) -> None:
    annotation_path(project_id, image_id).unlink(missing_ok=True)
    update_annotation_count(project_id, image_id, 0)
