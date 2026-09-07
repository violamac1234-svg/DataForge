from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from config import CLASS_COLORS, PROJECTS_DIR
from core.json_store import read_json, write_json_atomic


PROJECT_ID_PATTERN = re.compile(r"^proj_[0-9a-f]{8}$")


class ProjectError(ValueError):
    """Raised for invalid project operations."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_project_dir(project_id: str) -> Path:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ProjectError("项目 ID 非法。")
    return PROJECTS_DIR / project_id


def create_project(name: str, description: str, class_names: list[str]) -> dict[str, Any]:
    clean_name = name.strip()
    clean_classes = [item.strip() for item in class_names if item.strip()]
    if not clean_name:
        raise ProjectError("项目名称不能为空。")
    if not clean_classes:
        raise ProjectError("至少需要定义一个类别。")
    if len(set(clean_classes)) != len(clean_classes):
        raise ProjectError("类别名称不能重复。")

    while True:
        project_id = f"proj_{secrets.token_hex(4)}"
        project_dir = PROJECTS_DIR / project_id
        if not project_dir.exists():
            break

    for child in (
        "images",
        "thumbnails",
        "annotations",
        "datasets",
        "training_jobs",
        "models",
        "exports",
    ):
        (project_dir / child).mkdir(parents=True, exist_ok=True)

    timestamp = now_iso()
    project = {
        "schema_version": 1,
        "id": project_id,
        "name": clean_name,
        "description": description.strip(),
        "created_at": timestamp,
        "updated_at": timestamp,
        "classes": [
            {"id": index, "name": class_name, "color": CLASS_COLORS[index % len(CLASS_COLORS)]}
            for index, class_name in enumerate(clean_classes)
        ],
        "active_model": None,
    }
    write_json_atomic(project_dir / "project.json", project)
    write_json_atomic(project_dir / "images.json", {"schema_version": 1, "images": []})
    return project


def load_project(project_id: str) -> dict[str, Any]:
    project_dir = get_project_dir(project_id)
    project = read_json(project_dir / "project.json")
    if not isinstance(project, dict) or project.get("id") != project_id:
        raise ProjectError("项目不存在或项目配置已损坏。")
    if not project.get("classes"):
        raise ProjectError("项目类别为空。")
    return project


def list_projects() -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    if not PROJECTS_DIR.exists():
        return projects
    for path in PROJECTS_DIR.iterdir():
        if not path.is_dir() or not PROJECT_ID_PATTERN.fullmatch(path.name):
            continue
        try:
            projects.append(load_project(path.name))
        except Exception:
            continue
    return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)


def update_project(project_id: str, *, name: str | None = None, description: str | None = None) -> dict[str, Any]:
    project = load_project(project_id)
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ProjectError("项目名称不能为空。")
        project["name"] = clean_name
    if description is not None:
        project["description"] = description.strip()
    project["updated_at"] = now_iso()
    write_json_atomic(get_project_dir(project_id) / "project.json", project)
    return project


def set_active_model(project_id: str, model_id: str | None) -> dict[str, Any]:
    project = load_project(project_id)
    if model_id is not None and not (get_project_dir(project_id) / "models" / model_id / "best.pt").is_file():
        raise ProjectError("模型权重不存在，无法设为当前模型。")
    project["active_model"] = model_id
    project["updated_at"] = now_iso()
    write_json_atomic(get_project_dir(project_id) / "project.json", project)
    return project
