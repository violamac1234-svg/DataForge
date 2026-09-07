from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from core.json_store import read_json, write_json_atomic
from core.metrics_parser import latest_metrics
from core.project_manager import get_project_dir, load_project, set_active_model


MODEL_PATTERN = re.compile(r"^model_v(\d{3})$")


class ModelError(RuntimeError):
    """Raised when a training result cannot be registered as a model."""


def list_models(project_id: str) -> list[dict[str, Any]]:
    load_project(project_id)
    models = []
    for path in (get_project_dir(project_id) / "models").iterdir():
        if not path.is_dir() or not MODEL_PATTERN.fullmatch(path.name):
            continue
        data = read_json(path / "model.json")
        if isinstance(data, dict):
            models.append(data)
    return sorted(models, key=lambda item: item["id"], reverse=True)


def next_model_id(project_id: str) -> str:
    versions = []
    for path in (get_project_dir(project_id) / "models").iterdir():
        match = MODEL_PATTERN.fullmatch(path.name)
        if match:
            versions.append(int(match.group(1)))
    return f"model_v{max(versions, default=0) + 1:03d}"


def register_training_result(project_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Register a completed job exactly once and update the active model."""
    if job.get("status") != "completed":
        raise ModelError("只有 completed 训练任务可以注册模型。")
    for model in list_models(project_id):
        if model.get("training_job") == job["id"]:
            set_active_model(project_id, model["id"])
            return model

    job_dir = get_project_dir(project_id) / "training_jobs" / job["id"]
    run_dir = job_dir / "run"
    source_best = run_dir / "weights" / "best.pt"
    if not source_best.is_file():
        raise ModelError("训练结果缺少 best.pt。")
    model_id = next_model_id(project_id)
    model_dir = get_project_dir(project_id) / "models" / model_id
    model_dir.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copy2(source_best, model_dir / "best.pt")
        source_last = run_dir / "weights" / "last.pt"
        if source_last.is_file():
            shutil.copy2(source_last, model_dir / "last.pt")
        source_results = run_dir / "results.csv"
        if source_results.is_file():
            shutil.copy2(source_results, model_dir / "results.csv")
        metrics = latest_metrics(source_results) if source_results.is_file() else None
        project = load_project(project_id)
        base_name = Path(job["base_model"]).parent.name if "models" in Path(job["base_model"]).parts else Path(job["base_model"]).name
        model = {
            "schema_version": 1,
            "id": model_id,
            "name": f"Model V{int(model_id[-3:])}",
            "created_at": job.get("finished_at"),
            "training_job": job["id"],
            "base_model": base_name,
            "dataset_snapshot": job["id"],
            "training_config": {
                "epochs": job["epochs"],
                "batch": job["batch"],
                "imgsz": job["imgsz"],
                "device": job["device"],
                "train_ratio": job["train_ratio"],
            },
            "metrics": {
                "map50": metrics.get("map50") if metrics else None,
                "map5095": metrics.get("map5095") if metrics else None,
                "precision": metrics.get("precision") if metrics else None,
                "recall": metrics.get("recall") if metrics else None,
            },
            "classes": [{"id": item["id"], "name": item["name"]} for item in project["classes"]],
            "weights": {"best": "best.pt", "last": "last.pt" if (model_dir / "last.pt").is_file() else None},
        }
        write_json_atomic(model_dir / "model.json", model)
        set_active_model(project_id, model_id)
        return model
    except Exception:
        for child in model_dir.iterdir():
            child.unlink(missing_ok=True)
        model_dir.rmdir()
        raise


def activate_model(project_id: str, model_id: str) -> dict[str, Any]:
    if not any(model["id"] == model_id for model in list_models(project_id)):
        raise ModelError("模型版本不存在。")
    set_active_model(project_id, model_id)
    return load_project(project_id)
