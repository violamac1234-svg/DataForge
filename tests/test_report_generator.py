import core.project_manager as projects
from core.model_manager import register_training_result
from core.report_generator import generate_training_report


def test_html_report_uses_real_model_data(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    project = projects.create_project("钢板项目", "", ["scratch"])
    project_dir = projects.get_project_dir(project["id"])
    job_id = "job_report"
    run = project_dir / "training_jobs" / job_id / "run"
    (run / "weights").mkdir(parents=True)
    (run / "weights" / "best.pt").write_bytes(b"weights")
    (run / "results.csv").write_text(
        "epoch,train/box_loss,train/cls_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n0,0.4,0.3,0.8,0.7,0.75,0.5\n",
        encoding="utf-8",
    )
    job = {"id": job_id, "status": "completed", "finished_at": "now", "base_model": "base.pt", "epochs": 1, "batch": 1, "imgsz": 64, "device": "cpu", "train_ratio": 0.8}
    model = register_training_result(project["id"], job)
    result = generate_training_report(project["id"], model["id"])
    content = open(result["report_path"], encoding="utf-8").read()
    assert "钢板项目" in content
    assert "0.7500" in content
    assert "Loss 曲线" in content
    assert ">nan<" not in content.lower()
