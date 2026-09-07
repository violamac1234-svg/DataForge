from __future__ import annotations

import os
import socket
from pathlib import Path


APP_NAME = "炼数 DataForge V1.0"
HOST = "127.0.0.1"
PORT = int(os.environ.get("DATAFORGE_PORT", "8080"))

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
PROJECTS_DIR = STORAGE_DIR / "projects"
PRETRAINED_DIR = STORAGE_DIR / "pretrained"
LOG_DIR = BASE_DIR / "logs"

DEFAULT_EPOCHS = 100
DEFAULT_BATCH = 16
DEFAULT_IMGSZ = 640
DEFAULT_TRAIN_RATIO = 0.8
DATASET_SEED = 42

DEFAULT_CONFIDENCE_THRESHOLD = 0.25
LOW_CONFIDENCE_THRESHOLD = 0.60
HIGH_CONFIDENCE_THRESHOLD = 0.85

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CLASS_COLORS = [
    "#14B8A6",
    "#3B82F6",
    "#F59E0B",
    "#EF4444",
    "#8B5CF6",
    "#EC4899",
    "#22C55E",
    "#06B6D4",
    "#F97316",
]


def ensure_runtime_dirs() -> None:
    """Create the local runtime directories required by the application."""
    for path in (STORAGE_DIR, PROJECTS_DIR, PRETRAINED_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def available_port(preferred: int = PORT) -> int:
    """Return the preferred local port or the first available nearby port."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"无法在 {preferred}–{preferred + 19} 范围内找到可用端口。")
