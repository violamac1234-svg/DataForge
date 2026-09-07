from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from config import BASE_DIR, DEFAULT_BATCH, DEFAULT_EPOCHS, DEFAULT_IMGSZ, DEFAULT_TRAIN_RATIO, PRETRAINED_DIR
from core.dataset_builder import build_dataset
from core.json_store import read_json, write_json_atomic
from core.project_manager import get_project_dir, load_project, now_iso


class TrainingError(RuntimeError):
    """Raised for invalid or conflicting training operations."""


_PROCESSES: dict[str, subprocess.Popen] = {}
FINAL_STATES = {"completed", "failed", "stopped"}
ACTIVE_STATES = {"preparing", "running"}


def _jobs_dir(project_id: str) -> Path:
    load_project(project_id)
    return get_project_dir(project_id) / "training_jobs"


def _job_path(project_id: str, job_id: str) -> Path:
    if not job_id.startswith("job_") or any(char in job_id for char in "/\\.."):
        raise TrainingError("训练任务 ID 非法。")
    return _jobs_dir(project_id) / job_id / "job.json"


def list_jobs(project_id: str) -> list[dict[str, Any]]:
    jobs = []
    directory = _jobs_dir(project_id)
    for child in directory.iterdir():
        if child.is_dir() and child.name.startswith("job_"):
            job = read_json(child / "job.json")
            if isinstance(job, dict):
                jobs.append(job)
    return sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)


def load_job(project_id: str, job_id: str) -> dict[str, Any]:
    job = read_json(_job_path(project_id, job_id))
    if not isinstance(job, dict):
        raise TrainingError("训练任务不存在或已损坏。")
    return job


def available_base_models(project_id: str) -> dict[str, str]:
    project = load_project(project_id)
    options: dict[str, str] = {}
    active = project.get("active_model")
    if active:
        path = get_project_dir(project_id) / "models" / active / "best.pt"
        if path.is_file():
            options[str(path.resolve())] = f"当前模型 · {active}"
    for path in sorted(PRETRAINED_DIR.glob("*.pt")):
        options[str(path.resolve())] = f"基础权重 · {path.name}"
    return options


def _validate_config(epochs: int, batch: int, imgsz: int, train_ratio: float, device: str) -> None:
    if not 1 <= epochs <= 10000:
        raise TrainingError("Epoch 必须在 1 到 10000 之间。")
    if not 1 <= batch <= 1024:
        raise TrainingError("Batch Size 必须在 1 到 1024 之间。")
    if not 32 <= imgsz <= 4096:
        raise TrainingError("Image Size 必须在 32 到 4096 之间。")
    if not 0 < train_ratio < 1:
        raise TrainingError("Train Ratio 必须在 0 和 1 之间。")
    if device not in {"auto", "cpu"}:
        raise TrainingError("本机仅支持 Auto/CPU 训练。")


def _active_job(project_id: str) -> dict[str, Any] | None:
    for job in list_jobs(project_id):
        refreshed = refresh_job(project_id, job["id"]) if job.get("status") == "running" else job
        if refreshed.get("status") in ACTIVE_STATES:
            return refreshed
    return None


def start_training(
    project_id: str,
    *,
    base_model: str,
    epochs: int = DEFAULT_EPOCHS,
    batch: int = DEFAULT_BATCH,
    imgsz: int = DEFAULT_IMGSZ,
    device: str = "auto",
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict[str, Any]:
    _validate_config(epochs, batch, imgsz, train_ratio, device)
    if _active_job(project_id):
        raise TrainingError("当前已有训练任务正在运行。")
    base_path = Path(base_model).resolve()
    allowed = {Path(path).resolve() for path in available_base_models(project_id)}
    if base_path not in allowed or not base_path.is_file():
        raise TrainingError("请选择 storage/pretrained 中的基础权重或当前模型。")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = f"job_{stamp}_{secrets.token_hex(2)}"
    job_dir = _jobs_dir(project_id) / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    job_file = job_dir / "job.json"
    job = {
        "schema_version": 1,
        "id": job_id,
        "project_id": project_id,
        "status": "preparing",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "base_model": str(base_path),
        "epochs": epochs,
        "batch": batch,
        "imgsz": imgsz,
        "device": device,
        "train_ratio": train_ratio,
        "dataset_snapshot": None,
        "current_epoch": 0,
        "pid": None,
        "error": None,
    }
    write_json_atomic(job_file, job)
    try:
        snapshot = build_dataset(project_id, job_id, train_ratio=train_ratio)
        job["dataset_snapshot"] = str(snapshot.resolve())
        write_json_atomic(job_file, job)
        log_stream = (job_dir / "stdout.log").open("w", encoding="utf-8", buffering=1)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "core.training_worker", "--job-file", str(job_file.resolve())],
            cwd=BASE_DIR,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        log_stream.close()
        _PROCESSES[job_id] = process
        job.update({"status": "running", "started_at": now_iso(), "pid": process.pid})
        write_json_atomic(job_file, job)
        return job
    except Exception as exc:
        job.update({"status": "failed", "finished_at": now_iso(), "error": str(exc)})
        write_json_atomic(job_file, job)
        raise


def refresh_job(project_id: str, job_id: str) -> dict[str, Any]:
    job = load_job(project_id, job_id)
    if job["status"] != "running":
        return job
    result_csv = _job_path(project_id, job_id).parent / "run" / "results.csv"
    if result_csv.is_file():
        try:
            import pandas as pd

            rows = pd.read_csv(result_csv)
            job["current_epoch"] = len(rows)
        except Exception:
            pass
    process = _PROCESSES.get(job_id)
    exit_code = process.poll() if process else None
    pid_alive = bool(job.get("pid") and psutil.pid_exists(job["pid"]))
    if process is None and not pid_alive:
        result = read_json(_job_path(project_id, job_id).parent / "worker_result.json", {})
        exit_code = result.get("exit_code", 1)
    if exit_code is not None:
        result = read_json(_job_path(project_id, job_id).parent / "worker_result.json", {})
        best = _job_path(project_id, job_id).parent / "run" / "weights" / "best.pt"
        success = exit_code == 0 and result.get("exit_code") == 0 and best.is_file()
        job["status"] = "completed" if success else "failed"
        job["finished_at"] = result.get("finished_at") or now_iso()
        job["error"] = None if success else result.get("error", f"训练子进程退出码：{exit_code}")
        _PROCESSES.pop(job_id, None)
    write_json_atomic(_job_path(project_id, job_id), job)
    if job["status"] == "completed":
        try:
            from core.model_manager import register_training_result

            register_training_result(project_id, job)
        except Exception as exc:
            job.update({"status": "failed", "error": f"模型注册失败：{exc}"})
            write_json_atomic(_job_path(project_id, job_id), job)
    return job


def stop_training(project_id: str, job_id: str) -> dict[str, Any]:
    job = load_job(project_id, job_id)
    if job["status"] != "running":
        raise TrainingError("该任务当前不在训练中。")
    process = _PROCESSES.get(job_id)
    try:
        if process:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        elif job.get("pid") and psutil.pid_exists(job["pid"]):
            external = psutil.Process(job["pid"])
            external.terminate()
            try:
                external.wait(timeout=8)
            except psutil.TimeoutExpired:
                external.kill()
    finally:
        _PROCESSES.pop(job_id, None)
        job.update({"status": "stopped", "finished_at": now_iso(), "error": None})
        write_json_atomic(_job_path(project_id, job_id), job)
    return job


def tail_log(project_id: str, job_id: str, line_count: int = 160) -> str:
    path = _job_path(project_id, job_id).parent / "stdout.log"
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])
