from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

from core.annotation_manager import load_annotation, validate_annotation, xyxy_to_yolo
from core.image_manager import image_file_path, list_images
from core.json_store import read_json, write_json_atomic
from core.model_manager import list_models
from core.project_manager import get_project_dir, load_project, now_iso


class ExportError(RuntimeError):
    """Raised when project assets cannot be safely exported."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", name, flags=re.UNICODE).strip("_.")
    return cleaned or "DataForge"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _unique_dir(parent: Path, base_name: str) -> Path:
    candidate = parent / base_name
    index = 2
    while candidate.exists():
        candidate = parent / f"{base_name}_{index}"
        index += 1
    candidate.mkdir(parents=True)
    return candidate


def _zip_directory(source: Path, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(source))
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_checksum(archive: Path, checksum: str) -> Path:
    path = archive.with_suffix(archive.suffix + ".sha256")
    path.write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    return path


def export_dataset(project_id: str) -> dict[str, Any]:
    project = load_project(project_id)
    verified = [item for item in list_images(project_id, sort_by="oldest") if item["status"] == "verified"]
    if not verified:
        raise ExportError("没有 Verified 图片可供导出。")
    stamp = _timestamp()
    exports_dir = get_project_dir(project_id) / "exports"
    output = _unique_dir(exports_dir, f"dataset_{stamp}")
    try:
        (output / "images").mkdir()
        (output / "labels").mkdir()
        object_count = 0
        negative_count = 0
        for image in verified:
            source = image_file_path(project_id, image["id"])
            if not source.is_file():
                raise ExportError(f"图片文件缺失：{image['filename']}")
            annotation = load_annotation(project_id, image["id"])
            validate_annotation(project_id, annotation, expected_image_id=image["id"])
            shutil.copy2(source, output / "images" / image["stored_name"])
            lines = []
            for obj in annotation["objects"]:
                x, y, width, height = xyxy_to_yolo(obj["bbox"])
                lines.append(f"{obj['class_id']} {x:.8f} {y:.8f} {width:.8f} {height:.8f}")
            object_count += len(lines)
            negative_count += int(not lines)
            (output / "labels" / f"{Path(image['stored_name']).stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
        data_yaml = {"path": ".", "train": "images", "val": "images", "names": {c["id"]: c["name"] for c in project["classes"]}}
        with (output / "data.yaml").open("w", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(data_yaml, stream, allow_unicode=True, sort_keys=False)
        manifest = {
            "schema_version": 1,
            "project_id": project_id,
            "project_name": project["name"],
            "export_type": "dataset",
            "format": "yolo_detection",
            "created_at": now_iso(),
            "image_count": len(verified),
            "object_count": object_count,
            "negative_image_count": negative_count,
            "classes": [{"id": item["id"], "name": item["name"]} for item in project["classes"]],
        }
        write_json_atomic(output / "manifest.json", manifest)
        class_text = ", ".join(f"{item['id']}: {item['name']}" for item in project["classes"])
        (output / "README.txt").write_text(
            f"软件名称：炼数 DataForge V1.0\n项目名称：{project['name']}\n导出时间：{manifest['created_at']}\n"
            f"图片数量：{len(verified)}\n目标数量：{object_count}\n类别：{class_text}\n"
            "标注格式：YOLO Detection\n数据范围：Verified Only\n",
            encoding="utf-8",
        )
        archive = exports_dir / f"{_safe_name(project['name'])}_dataset_{stamp}.zip"
        _zip_directory(output, archive)
        checksum = sha256_file(archive)
        _write_checksum(archive, checksum)
        record = {
            "schema_version": 1,
            "id": f"export_{stamp}_dataset",
            "type": "dataset",
            "created_at": now_iso(),
            "artifact": archive.name,
            "sha256": checksum,
            "directory": output.name,
        }
        write_json_atomic(output / "export.json", record)
        return {**record, "archive_path": str(archive.resolve()), "output_dir": str(output.resolve())}
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


def export_model(project_id: str, model_id: str) -> dict[str, Any]:
    project = load_project(project_id)
    model = next((item for item in list_models(project_id) if item["id"] == model_id), None)
    if model is None:
        raise ExportError("所选模型不存在。")
    source = get_project_dir(project_id) / "models" / model_id
    if not (source / "best.pt").is_file():
        raise ExportError("模型缺少 best.pt。")
    stamp = _timestamp()
    exports_dir = get_project_dir(project_id) / "exports"
    output = _unique_dir(exports_dir, f"{model_id}_{stamp}")
    try:
        shutil.copy2(source / "best.pt", output / "best.pt")
        shutil.copy2(source / "model.json", output / "model.json")
        if (source / "results.csv").is_file():
            shutil.copy2(source / "results.csv", output / "metrics.csv")
        (output / "README.txt").write_text(
            f"软件名称：炼数 DataForge V1.0\n项目名称：{project['name']}\n模型版本：{model_id}\n"
            f"导出时间：{now_iso()}\n模型格式：Ultralytics PyTorch .pt\n",
            encoding="utf-8",
        )
        archive = exports_dir / f"{model_id}_{stamp}.zip"
        _zip_directory(output, archive)
        checksum = sha256_file(archive)
        _write_checksum(archive, checksum)
        record = {
            "schema_version": 1,
            "id": f"export_{stamp}_model",
            "type": "model",
            "model_id": model_id,
            "created_at": now_iso(),
            "artifact": archive.name,
            "sha256": checksum,
            "directory": output.name,
        }
        write_json_atomic(output / "export.json", record)
        return {**record, "archive_path": str(archive.resolve()), "output_dir": str(output.resolve())}
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise


def export_history(project_id: str) -> list[dict[str, Any]]:
    history = []
    for path in (get_project_dir(project_id) / "exports").glob("*/export.json"):
        record = read_json(path)
        if isinstance(record, dict):
            record = {**record, "record_path": str(path.resolve())}
            history.append(record)
    return sorted(history, key=lambda item: item.get("created_at", ""), reverse=True)
