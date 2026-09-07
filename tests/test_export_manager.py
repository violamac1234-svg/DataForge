import io
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

import core.project_manager as projects
from core.annotation_manager import verify_image
from core.export_manager import export_dataset, export_model, sha256_file
from core.image_manager import add_image_bytes
from core.model_manager import register_training_result


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "navy").save(buffer, "PNG")
    return buffer.getvalue()


def test_dataset_zip_and_sha256(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    project = projects.create_project("炼数 demo", "", ["object"])
    image = add_image_bytes(project["id"], "a.png", _png())
    verify_image(project["id"], image["id"], {"objects": [{
        "id": "obj_00000001", "class_id": 0, "bbox": [0, 0, 1, 1],
        "origin": "manual", "confidence": None, "edited": False,
    }]})
    record = export_dataset(project["id"])
    archive = Path(record["archive_path"])
    assert sha256_file(archive) == record["sha256"]
    with ZipFile(archive) as zipped:
        assert {"data.yaml", "manifest.json", "README.txt"}.issubset(zipped.namelist())


def test_model_zip_contains_pt(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    project = projects.create_project("demo", "", ["object"])
    project_dir = projects.get_project_dir(project["id"])
    run = project_dir / "training_jobs" / "job_one" / "run"
    (run / "weights").mkdir(parents=True)
    (run / "weights" / "best.pt").write_bytes(b"weights")
    job = {"id": "job_one", "status": "completed", "finished_at": "now", "base_model": "base.pt", "epochs": 1, "batch": 1, "imgsz": 64, "device": "cpu", "train_ratio": 0.8}
    model = register_training_result(project["id"], job)
    record = export_model(project["id"], model["id"])
    with ZipFile(record["archive_path"]) as zipped:
        assert "best.pt" in zipped.namelist()
        assert "model.json" in zipped.namelist()
