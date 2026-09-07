from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.json_store import read_json, write_json_atomic
from core.project_manager import now_iso


def run_training(job_file: Path) -> int:
    """Execute one Ultralytics training job outside the NiceGUI process."""
    job = read_json(job_file)
    if not isinstance(job, dict):
        raise RuntimeError("训练任务配置无法读取。")
    job_dir = job_file.parent
    result_file = job_dir / "worker_result.json"
    try:
        from ultralytics import YOLO

        model = YOLO(job["base_model"])
        model.train(
            data=str(Path(job["dataset_snapshot"]) / "data.yaml"),
            epochs=int(job["epochs"]),
            batch=int(job["batch"]),
            imgsz=int(job["imgsz"]),
            device="cpu" if job["device"] == "auto" else job["device"],
            project=str(job_dir),
            name="run",
            exist_ok=True,
            workers=0,
            plots=True,
        )
        best = job_dir / "run" / "weights" / "best.pt"
        if not best.is_file():
            raise RuntimeError("训练结束但未生成 best.pt。")
        write_json_atomic(result_file, {"exit_code": 0, "finished_at": now_iso(), "error": None})
        return 0
    except Exception as exc:
        write_json_atomic(
            result_file,
            {"exit_code": 1, "finished_at": now_iso(), "error": f"{type(exc).__name__}: {exc}"},
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="DataForge Ultralytics training worker")
    parser.add_argument("--job-file", type=Path, required=True)
    args = parser.parse_args()
    return run_training(args.job_file.resolve())


if __name__ == "__main__":
    sys.exit(main())
