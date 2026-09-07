from __future__ import annotations

import logging

from nicegui import app, ui

from config import APP_NAME, HOST, LOG_DIR, PORT, STORAGE_DIR, available_port, ensure_runtime_dirs
from pages.annotation import register_annotation_pages
from pages.dataset import register_dataset_pages
from pages.training import register_training_pages
from pages.export import register_export_pages


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> None:
    ensure_runtime_dirs()
    configure_logging()
    app.add_static_files("/storage", STORAGE_DIR)
    app.add_static_files("/static", STORAGE_DIR.parent / "static")
    register_dataset_pages()
    register_annotation_pages()
    register_training_pages()
    register_export_pages()
    selected_port = available_port(PORT)
    if selected_port != PORT:
        logging.getLogger(__name__).warning("Port %s is occupied; using %s instead", PORT, selected_port)
    ui.run(title=APP_NAME, host=HOST, port=selected_port, reload=False, show=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
