import io
import json

from PIL import Image

import core.project_manager as projects
from core.annotation_manager import verify_image
from core.dataset_builder import build_dataset
from core.image_manager import add_image_bytes


def _png(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (80, 60), color).save(buffer, "PNG")
    return buffer.getvalue()


def test_dataset_positive_negative_and_fixed_split(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    project = projects.create_project("steel", "", ["scratch", "crack"])
    for index in range(5):
        image = add_image_bytes(project["id"], f"{index}.png", _png(("red", "green", "blue", "white", "black")[index]))
        objects = [] if index == 4 else [{
            "id": f"obj_{index:08x}", "class_id": index % 2, "bbox": [0.1, 0.2, 0.5, 0.7],
            "origin": "manual", "confidence": None, "edited": False,
        }]
        verify_image(project["id"], image["id"], {"objects": objects})

    first = build_dataset(project["id"], "job_first", train_ratio=0.8, seed=42)
    second = build_dataset(project["id"], "job_second", train_ratio=0.8, seed=42)
    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert len(first_manifest["train_images"]) == 4
    assert len(first_manifest["val_images"]) == 1
    assert first_manifest["train_images"] == second_manifest["train_images"]
    assert first_manifest["negative_images"] == 1
    assert sum(first_manifest["class_counts"].values()) == 4
    label_files = list((first / "labels" / "train").glob("*.txt")) + list((first / "labels" / "val").glob("*.txt"))
    assert len(label_files) == 5
    assert any(path.read_text(encoding="utf-8") == "" for path in label_files)
