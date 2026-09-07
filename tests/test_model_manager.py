from pathlib import Path

import core.project_manager as projects
from core.model_manager import next_model_id, register_training_result


def _fake_job(project_id: str, job_id: str, project_dir: Path):
    run = project_dir / "training_jobs" / job_id / "run"
    (run / "weights").mkdir(parents=True)
    (run / "weights" / "best.pt").write_bytes(b"weights")
    (run / "weights" / "last.pt").write_bytes(b"last")
    (run / "results.csv").write_text(
        "epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n0,0.8,0.7,0.75,0.5\n",
        encoding="utf-8",
    )
    return {
        "id": job_id, "status": "completed", "finished_at": "2026-01-01T00:00:00+08:00",
        "base_model": "base.pt", "epochs": 1, "batch": 1, "imgsz": 64, "device": "cpu", "train_ratio": 0.8,
    }


def test_model_versions_increment_and_registration_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    project = projects.create_project("demo", "", ["object"])
    project_dir = projects.get_project_dir(project["id"])
    first_job = _fake_job(project["id"], "job_first", project_dir)
    first = register_training_result(project["id"], first_job)
    assert first["id"] == "model_v001"
    assert register_training_result(project["id"], first_job)["id"] == "model_v001"
    assert next_model_id(project["id"]) == "model_v002"
    second = register_training_result(project["id"], _fake_job(project["id"], "job_second", project_dir))
    assert second["id"] == "model_v002"
    assert projects.load_project(project["id"])["active_model"] == "model_v002"
