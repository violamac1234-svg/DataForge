from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import DEFAULT_CONFIDENCE_THRESHOLD
from core.annotation_manager import save_annotation
from core.image_manager import image_file_path, set_image_status
from core.project_manager import get_project_dir, load_project


class PredictionError(RuntimeError):
    """Raised when an active model cannot produce valid detections."""


@lru_cache(maxsize=3)
def _load_model(model_path: str):
    from ultralytics import YOLO

    return YOLO(model_path)


def _convert_result(result: Any) -> list[dict[str, Any]]:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return []
    xyxyn = boxes.xyxyn.cpu().tolist()
    class_ids = boxes.cls.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    predictions = []
    for bbox, class_id, confidence in zip(xyxyn, class_ids, confidences, strict=True):
        predictions.append(
            {
                "class_id": int(class_id),
                "bbox": [max(0.0, min(1.0, float(value))) for value in bbox],
                "confidence": float(confidence),
            }
        )
    return predictions


def predict(
    image_path: str | Path,
    model_path: str | Path,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Run a real Ultralytics prediction and return framework-neutral records."""
    image = Path(image_path)
    weights = Path(model_path)
    if not image.is_file():
        raise PredictionError("待预测图片不存在。")
    if not weights.is_file():
        raise PredictionError("当前模型文件不存在。")
    try:
        model = _load_model(str(weights.resolve()))
        results = model.predict(source=str(image), conf=confidence_threshold, device="cpu", verbose=False)
        return _convert_result(results[0]) if results else []
    except Exception as exc:
        raise PredictionError("Ultralytics 推理失败，请检查模型与图片。") from exc


def active_model_path(project_id: str) -> Path:
    project = load_project(project_id)
    model_id = project.get("active_model")
    if not model_id:
        raise PredictionError("当前项目尚未配置检测模型。")
    path = get_project_dir(project_id) / "models" / model_id / "best.pt"
    if not path.is_file():
        raise PredictionError("当前模型文件不存在。")
    return path


def prelabel_image(project_id: str, image_id: str, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> list[dict[str, Any]]:
    predictions = predict(image_file_path(project_id, image_id), active_model_path(project_id), confidence_threshold)
    objects = [
        {
            "id": f"obj_{secrets.token_hex(4)}",
            "class_id": item["class_id"],
            "bbox": item["bbox"],
            "origin": "ai",
            "confidence": item["confidence"],
            "edited": False,
        }
        for item in predictions
    ]
    save_annotation(project_id, image_id, {"objects": objects})
    set_image_status(project_id, image_id, "prelabeled")
    return objects
