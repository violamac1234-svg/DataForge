from __future__ import annotations

import io
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError

from config import SUPPORTED_IMAGE_EXTENSIONS
from core.json_store import read_json, write_json_atomic
from core.project_manager import get_project_dir, load_project, now_iso


ImageStatus = Literal["unlabeled", "prelabeled", "verified", "discarded"]
VALID_STATUSES = {"unlabeled", "prelabeled", "verified", "discarded"}


class ImageManagerError(ValueError):
    """Raised for invalid image operations."""


def _images_file(project_id: str) -> Path:
    return get_project_dir(project_id) / "images.json"


def _load_document(project_id: str) -> dict[str, Any]:
    load_project(project_id)
    document = read_json(_images_file(project_id), {"schema_version": 1, "images": []})
    if not isinstance(document, dict) or not isinstance(document.get("images"), list):
        raise ImageManagerError("图片索引已损坏。")
    return document


def list_images(
    project_id: str,
    *,
    search: str = "",
    status: str = "all",
    sort_by: str = "newest",
) -> list[dict[str, Any]]:
    images = list(_load_document(project_id)["images"])
    needle = search.strip().casefold()
    if needle:
        images = [item for item in images if needle in str(item.get("filename", "")).casefold()]
    if status != "all":
        if status not in VALID_STATUSES:
            raise ImageManagerError("图片状态筛选值非法。")
        images = [item for item in images if item.get("status") == status]
    if sort_by == "filename":
        return sorted(images, key=lambda item: str(item.get("filename", "")).casefold())
    if sort_by == "oldest":
        return sorted(images, key=lambda item: item.get("created_at", ""))
    return sorted(images, key=lambda item: item.get("created_at", ""), reverse=True)


def get_image(project_id: str, image_id: str) -> dict[str, Any]:
    for record in _load_document(project_id)["images"]:
        if record.get("id") == image_id:
            return record
    raise ImageManagerError("图片不存在。")


def add_image_bytes(project_id: str, filename: str, content: bytes) -> dict[str, Any]:
    document = _load_document(project_id)
    safe_filename = Path(filename).name
    extension = Path(safe_filename).suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ImageManagerError("不支持该图片格式。")
    if not content:
        raise ImageManagerError("图片文件为空。")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            width, height = source.size
            thumbnail = source.convert("RGB")
            thumbnail.thumbnail((480, 320), Image.Resampling.LANCZOS)
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(thumbnail_buffer, format="JPEG", quality=84, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageManagerError("图片损坏或无法识别。") from exc

    project_dir = get_project_dir(project_id)
    image_id = f"img_{secrets.token_hex(4)}"
    stored_name = f"{image_id}{extension}"
    image_path = project_dir / "images" / stored_name
    thumbnail_path = project_dir / "thumbnails" / f"{image_id}.jpg"
    temp_paths: list[Path] = []
    try:
        for target, payload in ((image_path, content), (thumbnail_path, thumbnail_buffer.getvalue())):
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
                temporary = Path(stream.name)
            temp_paths.append(temporary)
            os.replace(temporary, target)
            temp_paths.remove(temporary)

        timestamp = now_iso()
        record = {
            "id": image_id,
            "filename": safe_filename,
            "stored_name": stored_name,
            "width": width,
            "height": height,
            "status": "unlabeled",
            "annotation_count": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        document["images"].append(record)
        write_json_atomic(_images_file(project_id), document)
        return record
    except Exception:
        image_path.unlink(missing_ok=True)
        thumbnail_path.unlink(missing_ok=True)
        for temporary in temp_paths:
            temporary.unlink(missing_ok=True)
        raise


def set_image_status(project_id: str, image_id: str, status: ImageStatus) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ImageManagerError("图片状态非法。")
    document = _load_document(project_id)
    for record in document["images"]:
        if record.get("id") == image_id:
            record["status"] = status
            record["updated_at"] = now_iso()
            write_json_atomic(_images_file(project_id), document)
            return record
    raise ImageManagerError("图片不存在。")


def update_annotation_count(project_id: str, image_id: str, count: int) -> None:
    document = _load_document(project_id)
    for record in document["images"]:
        if record.get("id") == image_id:
            record["annotation_count"] = max(0, int(count))
            record["updated_at"] = now_iso()
            write_json_atomic(_images_file(project_id), document)
            return
    raise ImageManagerError("图片不存在。")


def delete_image(project_id: str, image_id: str) -> None:
    document = _load_document(project_id)
    matches = [item for item in document["images"] if item.get("id") == image_id]
    if not matches:
        raise ImageManagerError("图片不存在。")
    record = matches[0]
    project_dir = get_project_dir(project_id)
    document["images"] = [item for item in document["images"] if item.get("id") != image_id]
    write_json_atomic(_images_file(project_id), document)
    (project_dir / "images" / record["stored_name"]).unlink(missing_ok=True)
    (project_dir / "thumbnails" / f"{image_id}.jpg").unlink(missing_ok=True)
    (project_dir / "annotations" / f"{image_id}.json").unlink(missing_ok=True)


def stats(project_id: str) -> dict[str, int]:
    images = _load_document(project_id)["images"]
    result = {"total": len(images), **{status: 0 for status in VALID_STATUSES}}
    for item in images:
        status = item.get("status")
        if status in VALID_STATUSES:
            result[status] += 1
    return result


def image_file_path(project_id: str, image_id: str) -> Path:
    record = get_image(project_id, image_id)
    return get_project_dir(project_id) / "images" / record["stored_name"]


def thumbnail_url(project_id: str, image_id: str) -> str:
    get_image(project_id, image_id)
    return f"/storage/projects/{project_id}/thumbnails/{image_id}.jpg"
